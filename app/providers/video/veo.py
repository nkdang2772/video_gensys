from __future__ import annotations

import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image

from app.providers.video.base import (
    VideoProvider,
    VideoProviderError,
    VideoProviderTimeoutError,
    validate_mp4_file,
    video_output_path,
    validate_source_image,
)

GEMINI_API_KEY_ENV = "GEMINI_API_KEY"


class VeoVideoProvider(VideoProvider):
    name = "veo_cloud"

    def __init__(self, *, api_key: str | None = None, client: Any | None = None) -> None:
        self.api_key = api_key or os.getenv(GEMINI_API_KEY_ENV)
        self.client = client

    def _client(self) -> Any:
        if self.client is not None:
            return self.client
        if not self.api_key:
            raise VideoProviderError(f"{GEMINI_API_KEY_ENV} is required for Veo")
        try:
            from google import genai
        except ImportError as exc:
            raise VideoProviderError(
                "Veo requires the optional dependency: pip install -e .[veo]"
            ) from exc
        self.client = genai.Client(api_key=self.api_key)
        return self.client

    def generate(self, source_image: Path, prompt: str, config: Mapping[str, Any]) -> Path:
        source = validate_source_image(source_image)
        if not prompt.strip():
            raise VideoProviderError("Veo prompt cannot be empty")
        client = self._client()
        model = str(config.get("model") or "veo-3.1-generate-preview")
        total_timeout = float(config.get("timeout_sec", 1800.0))
        poll_interval = float(config.get("poll_interval_sec", 10.0))
        if total_timeout <= 0 or poll_interval < 0:
            raise VideoProviderError("Veo timeout values are invalid")
        generation_config = {
            key: config[key]
            for key in ("negative_prompt", "aspect_ratio", "resolution", "duration_seconds")
            if config.get(key) is not None
        }
        try:
            with Image.open(source) as opened:
                image = opened.copy()
            operation = client.models.generate_videos(
                model=model,
                prompt=prompt.strip(),
                image=image,
                config=generation_config or None,
            )
            deadline = time.monotonic() + total_timeout
            while not operation.done and time.monotonic() < deadline:
                time.sleep(poll_interval)
                operation = client.operations.get(operation)
            if not operation.done:
                raise VideoProviderTimeoutError("Veo generation timed out")
            generated = operation.response.generated_videos[0]
            client.files.download(file=generated.video)
            destination = video_output_path(config)
            if destination.exists():
                raise VideoProviderError(f"Video provider output already exists: {destination}")
            temporary = destination.with_name(f".{destination.stem}.{os.getpid()}.tmp.mp4")
            temporary.unlink(missing_ok=True)
            try:
                generated.video.save(str(temporary))
                validate_mp4_file(temporary)
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        except VideoProviderError:
            raise
        except Exception as exc:
            raise VideoProviderError(f"Veo generation failed: {exc}") from exc
        return destination

    def cost(self, config: Mapping[str, Any]):
        configured = dict(config)
        configured.setdefault("cost_credit_type", "veo")
        configured.setdefault("cost_is_estimated", True)
        return super().cost(configured)
