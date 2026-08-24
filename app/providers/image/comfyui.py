from __future__ import annotations

import copy
import json
import socket
import time
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.providers.image.base import ImageProvider, ProviderError, ProviderTimeoutError, output_path, write_png_atomic


def _request(url: str, *, payload: dict[str, Any] | None, timeout: float) -> bytes:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method="POST" if data is not None else "GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except (TimeoutError, socket.timeout) as exc:
        raise ProviderTimeoutError("ComfyUI request timed out") from exc
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise ProviderError(f"ComfyUI HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise ProviderTimeoutError("ComfyUI request timed out") from exc
        raise ProviderError(f"ComfyUI connection failed: {exc.reason}") from exc


def _upload_image(base_url: str, source: Path, timeout: float) -> str:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise ProviderError(f"Reference image does not exist: {source}")
    if any(character in source.name for character in ('"', "\r", "\n")):
        raise ProviderError("Reference filename contains unsafe multipart characters")
    boundary = f"----VideoGenSystem{uuid.uuid4().hex}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{source.name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8") + source.read_bytes() + (
        f"\r\n--{boundary}\r\n"
        'Content-Disposition: form-data; name="type"\r\n\r\ninput\r\n'
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n'
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    request = Request(
        f"{base_url}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            uploaded = json.loads(response.read().decode("utf-8"))
    except (TimeoutError, socket.timeout) as exc:
        raise ProviderTimeoutError("ComfyUI reference upload timed out") from exc
    except (HTTPError, URLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProviderError(f"ComfyUI reference upload failed: {exc}") from exc
    name = uploaded.get("name")
    if not isinstance(name, str) or not name:
        raise ProviderError("ComfyUI returned an invalid reference upload response")
    subfolder = uploaded.get("subfolder")
    return f"{subfolder}/{name}" if subfolder else name


def _replace_prompt(value: Any, prompt: str) -> tuple[Any, bool]:
    if isinstance(value, str):
        return value.replace("{{PROMPT}}", prompt), "{{PROMPT}}" in value
    if isinstance(value, list):
        replaced = [_replace_prompt(item, prompt) for item in value]
        return [item[0] for item in replaced], any(item[1] for item in replaced)
    if isinstance(value, dict):
        replaced = {key: _replace_prompt(item, prompt) for key, item in value.items()}
        return {key: item[0] for key, item in replaced.items()}, any(item[1][1] for item in replaced.items())
    return value, False


class ComfyUIImageProvider(ImageProvider):
    name = "comfyui"

    def __init__(self, *, base_url: str = "http://127.0.0.1:8188") -> None:
        self.base_url = base_url.rstrip("/")

    def generate(
        self,
        prompt: str,
        reference_images: Sequence[Path],
        config: Mapping[str, Any],
    ) -> Path:
        base_url = str(config.get("base_url") or self.base_url).rstrip("/")
        workflow_value = config.get("workflow")
        if workflow_value is None and config.get("workflow_path"):
            try:
                workflow_value = json.loads(Path(str(config["workflow_path"])).read_text("utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ProviderError("Could not load ComfyUI workflow JSON") from exc
        if not isinstance(workflow_value, dict):
            raise ProviderError("ComfyUI config requires workflow or workflow_path")
        workflow = copy.deepcopy(workflow_value)
        prompt_node = config.get("prompt_node_id")
        if prompt_node is not None:
            try:
                workflow[str(prompt_node)]["inputs"][str(config.get("prompt_input", "text"))] = prompt
            except (KeyError, TypeError) as exc:
                raise ProviderError("ComfyUI prompt node/input was not found") from exc
        else:
            workflow, replaced = _replace_prompt(workflow, prompt)
            if not replaced:
                raise ProviderError("Workflow needs {{PROMPT}} or prompt_node_id")
        request_timeout = float(config.get("request_timeout_sec", 30.0))
        total_timeout = float(config.get("timeout_sec", 600.0))
        poll_interval = float(config.get("poll_interval_sec", 1.0))
        if min(request_timeout, total_timeout) <= 0 or poll_interval < 0:
            raise ProviderError("ComfyUI timeout values must be positive")
        reference_nodes = config.get("reference_image_nodes", [])
        if isinstance(reference_nodes, str):
            try:
                reference_nodes = json.loads(reference_nodes)
            except json.JSONDecodeError as exc:
                raise ProviderError("reference_image_nodes must be valid JSON") from exc
        if not isinstance(reference_nodes, list) or len(reference_nodes) != len(reference_images):
            if reference_images:
                raise ProviderError(
                    "reference_image_nodes must map every reference image to a ComfyUI LoadImage node"
                )
        for source, mapping in zip(reference_images, reference_nodes):
            if isinstance(mapping, str):
                node_id, input_name = mapping, "image"
            elif isinstance(mapping, dict):
                node_id = str(mapping.get("node_id", ""))
                input_name = str(mapping.get("input", "image"))
            else:
                raise ProviderError("Invalid ComfyUI reference node mapping")
            try:
                workflow[node_id]["inputs"][input_name] = _upload_image(
                    base_url, Path(source), request_timeout
                )
            except (KeyError, TypeError) as exc:
                raise ProviderError(f"ComfyUI reference node was not found: {node_id}") from exc
        try:
            submitted = json.loads(
                _request(
                    f"{base_url}/prompt",
                    payload={"prompt": workflow, "client_id": uuid.uuid4().hex},
                    timeout=request_timeout,
                ).decode("utf-8")
            )
            prompt_id = str(submitted["prompt_id"])
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError) as exc:
            raise ProviderError("ComfyUI returned an invalid prompt response") from exc

        deadline = time.monotonic() + total_timeout
        history_entry: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            try:
                history = json.loads(
                    _request(
                        f"{base_url}/history/{prompt_id}",
                        payload=None,
                        timeout=request_timeout,
                    ).decode("utf-8")
                )
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ProviderError("ComfyUI returned invalid history JSON") from exc
            if isinstance(history.get(prompt_id), dict):
                history_entry = history[prompt_id]
                break
            time.sleep(poll_interval)
        if history_entry is None:
            raise ProviderTimeoutError(f"ComfyUI workflow timed out: {prompt_id}")

        images: list[dict[str, Any]] = []
        for node_output in history_entry.get("outputs", {}).values():
            images.extend(node_output.get("images", []))
        if not images:
            raise ProviderError("ComfyUI history contains no output image")
        image = images[-1]
        query = urlencode(
            {
                "filename": image["filename"],
                "subfolder": image.get("subfolder", ""),
                "type": image.get("type", "output"),
            }
        )
        data = _request(f"{base_url}/view?{query}", payload=None, timeout=request_timeout)
        return write_png_atomic(output_path(config), data)
