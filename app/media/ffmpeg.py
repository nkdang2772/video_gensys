from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

FFMPEG_PATH_ENV = "VIDEO_GENSYSTEM_FFMPEG_PATH"


class FFmpegError(RuntimeError):
    pass


def resolve_ffmpeg(ffmpeg_path: str | Path | None = None) -> str:
    configured = str(ffmpeg_path or os.getenv(FFMPEG_PATH_ENV, "")).strip()
    if configured:
        path = Path(configured).expanduser().resolve()
        if not path.is_file():
            raise FFmpegError(f"ffmpeg executable does not exist: {path}")
        return str(path)
    discovered = shutil.which("ffmpeg")
    if discovered is None:
        raise FFmpegError(f"ffmpeg was not found; configure {FFMPEG_PATH_ENV} or add it to PATH")
    return discovered


def run_ffmpeg(
    arguments: Sequence[str],
    *,
    ffmpeg_path: str | Path | None = None,
    timeout_sec: float = 300.0,
) -> None:
    if timeout_sec <= 0:
        raise ValueError("timeout_sec must be greater than zero")
    command = [
        resolve_ffmpeg(ffmpeg_path),
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        *arguments,
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"ffmpeg timed out after {timeout_sec:g} seconds") from exc
    except OSError as exc:
        raise FFmpegError(f"Could not execute ffmpeg: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip()[-4000:] or f"exit code {result.returncode}"
        raise FFmpegError(f"ffmpeg failed: {detail}")
