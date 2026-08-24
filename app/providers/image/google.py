from __future__ import annotations

import base64
import json
import mimetypes
import os
import socket
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.providers.image.base import ImageProvider, ProviderError, ProviderTimeoutError, output_path, write_png_atomic

JsonTransport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


def _default_transport(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (TimeoutError, socket.timeout) as exc:
        raise ProviderTimeoutError("Gemini image request timed out") from exc
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise ProviderError(f"Gemini HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise ProviderTimeoutError("Gemini image request timed out") from exc
        raise ProviderError(f"Gemini connection failed: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProviderError("Gemini returned invalid JSON") from exc


class GoogleImageProvider(ImageProvider):
    name = "google"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gemini-3.1-flash-image",
        transport: JsonTransport | None = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1",
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model
        self.transport = transport or _default_transport
        self.base_url = base_url.rstrip("/")

    def generate(
        self,
        prompt: str,
        reference_images: Sequence[Path],
        config: Mapping[str, Any],
    ) -> Path:
        if not self.api_key:
            raise ProviderError("GEMINI_API_KEY is not configured")
        if not prompt.strip():
            raise ProviderError("Image prompt cannot be empty")
        parts: list[dict[str, Any]] = [{"text": prompt.strip()}]
        for reference in reference_images:
            source = Path(reference).expanduser().resolve()
            if not source.is_file():
                raise ProviderError(f"Reference image does not exist: {source}")
            mime_type = mimetypes.guess_type(source.name)[0] or "image/png"
            parts.append(
                {
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": base64.b64encode(source.read_bytes()).decode("ascii"),
                    }
                }
            )
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        }
        model = str(config.get("model") or self.model)
        timeout = float(config.get("timeout_sec", 120.0))
        if timeout <= 0:
            raise ProviderError("timeout_sec must be positive")
        response = self.transport(
            f"{self.base_url}/models/{model}:generateContent",
            {"Content-Type": "application/json", "x-goog-api-key": self.api_key},
            payload,
            timeout,
        )
        images: list[bytes] = []
        for candidate in response.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline = part.get("inlineData") or part.get("inline_data")
                if part.get("thought") or not isinstance(inline, dict):
                    continue
                if inline.get("mimeType", inline.get("mime_type")) != "image/png":
                    continue
                try:
                    images.append(base64.b64decode(inline["data"], validate=True))
                except (KeyError, ValueError) as exc:
                    raise ProviderError("Gemini returned invalid image data") from exc
        if not images:
            raise ProviderError("Gemini response did not contain a final PNG image")
        return write_png_atomic(output_path(config), images[-1])
