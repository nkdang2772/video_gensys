from __future__ import annotations

import copy
import json
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from app.providers.image.base import ProviderError as ImageProviderError
from app.providers.image.base import ProviderTimeoutError as ImageProviderTimeoutError
from app.providers.image.comfyui import _request as _image_request
from app.providers.image.comfyui import _upload_image as _image_upload
from app.providers.video.base import (
    VideoProvider,
    VideoProviderError,
    VideoProviderTimeoutError,
    video_output_path,
    validate_source_image,
    write_mp4_atomic,
)


def _request(url: str, *, payload: dict[str, Any] | None, timeout: float) -> bytes:
    try:
        return _image_request(url, payload=payload, timeout=timeout)
    except ImageProviderTimeoutError as exc:
        raise VideoProviderTimeoutError(str(exc)) from exc
    except ImageProviderError as exc:
        raise VideoProviderError(str(exc)) from exc


def _upload_image(base_url: str, source: Path, timeout: float) -> str:
    try:
        return _image_upload(base_url, source, timeout)
    except ImageProviderTimeoutError as exc:
        raise VideoProviderTimeoutError(str(exc)) from exc
    except ImageProviderError as exc:
        raise VideoProviderError(str(exc)) from exc


def _replace_prompt(value: Any, prompt: str) -> tuple[Any, bool]:
    if isinstance(value, str):
        return value.replace("{{PROMPT}}", prompt), "{{PROMPT}}" in value
    if isinstance(value, list):
        converted = [_replace_prompt(item, prompt) for item in value]
        return [item[0] for item in converted], any(item[1] for item in converted)
    if isinstance(value, dict):
        converted = {key: _replace_prompt(item, prompt) for key, item in value.items()}
        return {key: item[0] for key, item in converted.items()}, any(
            item[1] for item in converted.values()
        )
    return value, False


class WanVideoProvider(VideoProvider):
    name = "wan_local"

    def __init__(self, *, base_url: str = "http://127.0.0.1:8188") -> None:
        self.base_url = base_url.rstrip("/")

    def generate(self, source_image: Path, prompt: str, config: Mapping[str, Any]) -> Path:
        source = validate_source_image(source_image)
        if not prompt.strip():
            raise VideoProviderError("Wan prompt cannot be empty")
        base_url = str(config.get("base_url") or self.base_url).rstrip("/")
        workflow_value = config.get("workflow")
        if workflow_value is None and config.get("workflow_path"):
            try:
                workflow_value = json.loads(Path(str(config["workflow_path"])).read_text("utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise VideoProviderError("Could not load Wan ComfyUI workflow JSON") from exc
        if not isinstance(workflow_value, dict):
            raise VideoProviderError("Wan config requires workflow or workflow_path")
        workflow = copy.deepcopy(workflow_value)
        prompt_node = config.get("prompt_node_id")
        if prompt_node is not None:
            try:
                workflow[str(prompt_node)]["inputs"][str(config.get("prompt_input", "text"))] = prompt
            except (KeyError, TypeError) as exc:
                raise VideoProviderError("Wan prompt node/input was not found") from exc
        else:
            workflow, replaced = _replace_prompt(workflow, prompt)
            if not replaced:
                raise VideoProviderError("Wan workflow needs {{PROMPT}} or prompt_node_id")
        image_node = str(config.get("source_image_node_id") or "").strip()
        if not image_node:
            raise VideoProviderError("Wan config requires source_image_node_id")
        request_timeout = float(config.get("request_timeout_sec", 30.0))
        total_timeout = float(config.get("timeout_sec", 1800.0))
        poll_interval = float(config.get("poll_interval_sec", 2.0))
        if request_timeout <= 0 or total_timeout <= 0 or poll_interval < 0:
            raise VideoProviderError("Wan timeout values are invalid")
        uploaded_name = _upload_image(base_url, source, request_timeout)
        try:
            workflow[image_node]["inputs"][str(config.get("source_image_input", "image"))] = uploaded_name
        except (KeyError, TypeError) as exc:
            raise VideoProviderError(f"Wan source image node was not found: {image_node}") from exc
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
            raise VideoProviderError("ComfyUI returned an invalid Wan prompt response") from exc
        deadline = time.monotonic() + total_timeout
        history_entry: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            try:
                history = json.loads(
                    _request(
                        f"{base_url}/history/{prompt_id}", payload=None, timeout=request_timeout
                    ).decode("utf-8")
                )
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise VideoProviderError("ComfyUI returned invalid Wan history JSON") from exc
            if isinstance(history.get(prompt_id), dict):
                history_entry = history[prompt_id]
                break
            time.sleep(poll_interval)
        if history_entry is None:
            raise VideoProviderTimeoutError(f"Wan workflow timed out: {prompt_id}")
        outputs: list[dict[str, Any]] = []
        for node_output in history_entry.get("outputs", {}).values():
            for key in ("videos", "gifs", "images"):
                values = node_output.get(key, []) if isinstance(node_output, dict) else []
                if isinstance(values, list):
                    outputs.extend(item for item in values if isinstance(item, dict))
        media = next(
            (item for item in reversed(outputs) if str(item.get("filename", "")).lower().endswith(".mp4")),
            None,
        )
        if media is None:
            raise VideoProviderError("Wan history contains no MP4 output")
        query = urlencode(
            {
                "filename": media["filename"],
                "subfolder": media.get("subfolder", ""),
                "type": media.get("type", "output"),
            }
        )
        data = _request(f"{base_url}/view?{query}", payload=None, timeout=request_timeout)
        return write_mp4_atomic(video_output_path(config), data)
