from __future__ import annotations

import base64
import hmac
import json
import mimetypes
import os
import threading
import uuid
from collections.abc import Mapping, Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app.providers.image.base import (
    ImageProvider,
    ProviderError,
    ProviderTimeoutError,
    copy_png_atomic,
    output_path,
)

FLOW_BRIDGE_TOKEN_ENV = "VIDEO_GENSYSTEM_FLOW_BRIDGE_TOKEN"
DEFAULT_BRIDGE_PORT = 8765
MAX_RESULT_BYTES = 1024 * 1024


class _BridgeState:
    def __init__(self, task: dict[str, Any], token: str) -> None:
        self.task = task
        self.token = token
        self.claimed = False
        self.result: dict[str, Any] | None = None
        self.completed = threading.Event()
        self.lock = threading.Lock()


class _BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _handler_for(state: _BridgeState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _authorized(self) -> bool:
            supplied = self.headers.get("X-VideoGenSystem-Token", "")
            return hmac.compare_digest(supplied, state.token)

        def _json(self, status: int, payload: dict[str, Any] | None = None) -> None:
            data = json.dumps(payload or {}).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorized():
                self._json(401, {"error": "unauthorized"})
                return
            if self.path == "/v1/health":
                self._json(200, {"ok": True})
                return
            if self.path != "/v1/tasks/next":
                self._json(404, {"error": "not_found"})
                return
            with state.lock:
                if state.claimed or state.result is not None:
                    self.send_response(204)
                    self.end_headers()
                    return
                state.claimed = True
                task = state.task
            self._json(200, task)

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorized():
                self._json(401, {"error": "unauthorized"})
                return
            expected = f"/v1/tasks/{state.task['id']}/result"
            if self.path != expected:
                self._json(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._json(400, {"error": "invalid_length"})
                return
            if length <= 0 or length > MAX_RESULT_BYTES:
                self._json(413, {"error": "invalid_result_size"})
                return
            try:
                result = json.loads(self.rfile.read(length).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._json(400, {"error": "invalid_json"})
                return
            if not isinstance(result, dict):
                self._json(400, {"error": "invalid_result"})
                return
            with state.lock:
                if state.result is not None:
                    self._json(409, {"error": "already_completed"})
                    return
                state.result = result
                state.completed.set()
            self._json(200, {"ok": True})

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return Handler


class GoogleFlowImageProvider(ImageProvider):
    """Generate through the user's h2dev_flow Chrome extension, not a Google API."""

    name = "google_flow"

    def __init__(self, *, bridge_token: str | None = None) -> None:
        self.bridge_token = bridge_token or os.getenv(FLOW_BRIDGE_TOKEN_ENV)

    def generate(
        self,
        prompt: str,
        reference_images: Sequence[Path],
        config: Mapping[str, Any],
    ) -> Path:
        if not prompt.strip():
            raise ProviderError("Image prompt cannot be empty")
        if not self.bridge_token or len(self.bridge_token) < 16:
            raise ProviderError(
                f"{FLOW_BRIDGE_TOKEN_ENV} must contain at least 16 characters"
            )
        host = str(config.get("bridge_host", "127.0.0.1"))
        if host not in {"127.0.0.1", "localhost"}:
            raise ProviderError("Google Flow bridge may only bind to localhost")
        port = int(config.get("bridge_port", DEFAULT_BRIDGE_PORT))
        if not 1 <= port <= 65535:
            raise ProviderError("bridge_port must be between 1 and 65535")
        timeout = float(config.get("timeout_sec", 600.0))
        if timeout <= 0:
            raise ProviderError("timeout_sec must be positive")
        downloads_root = Path(
            str(config.get("downloads_root") or (Path.home() / "Downloads"))
        ).expanduser().resolve()
        task_id = uuid.uuid4().hex
        relative_download = Path("video_gensystem_bridge") / f"{task_id}.png"
        references: list[dict[str, str]] = []
        for source_value in reference_images:
            source = Path(source_value).expanduser().resolve()
            if not source.is_file():
                raise ProviderError(f"Pinned reference image does not exist: {source}")
            mime_type = mimetypes.guess_type(source.name)[0] or "image/png"
            if not mime_type.startswith("image/"):
                raise ProviderError(f"Pinned reference is not an image: {source}")
            references.append(
                {
                    "name": source.name,
                    "mime_type": mime_type,
                    "data_url": f"data:{mime_type};base64,"
                    + base64.b64encode(source.read_bytes()).decode("ascii"),
                }
            )
        task = {
            "id": task_id,
            "prompt": prompt.strip(),
            "references": references,
            "download_path": relative_download.as_posix(),
        }
        state = _BridgeState(task, self.bridge_token)
        try:
            server = _BridgeServer((host, port), _handler_for(state))
        except OSError as exc:
            raise ProviderError(f"Could not start Google Flow bridge on {host}:{port}: {exc}") from exc
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            if not state.completed.wait(timeout):
                raise ProviderTimeoutError(
                    "Google Flow extension did not complete the task before timeout"
                )
            result = state.result or {}
            if not result.get("ok"):
                message = str(result.get("error") or "Google Flow extension reported an error")
                if result.get("timeout"):
                    raise ProviderTimeoutError(message)
                raise ProviderError(message)
            returned_path = result.get("download_path")
            if returned_path != relative_download.as_posix():
                raise ProviderError("Google Flow extension returned an unexpected download path")
            downloaded = (downloads_root / relative_download).resolve()
            try:
                downloaded.relative_to(downloads_root)
            except ValueError as exc:
                raise ProviderError("Google Flow download escaped Downloads root") from exc
            if not downloaded.is_file():
                raise ProviderError(f"Google Flow download was not found: {downloaded}")
            destination = copy_png_atomic(downloaded, output_path(config))
            if bool(config.get("cleanup_bridge_download", True)):
                downloaded.unlink(missing_ok=True)
            return destination
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=2)


# Backward-compatible import name; it now uses Flow and never calls Gemini.
GoogleImageProvider = GoogleFlowImageProvider
