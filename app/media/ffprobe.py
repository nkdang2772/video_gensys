from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FFPROBE_PATH_ENV = "VIDEO_GENSYSTEM_FFPROBE_PATH"


class FFprobeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AudioMetadata:
    duration_sec: float
    sample_rate: int
    channels: int
    codec: str


def _resolve_executable(ffprobe_path: str | Path | None) -> str:
    configured = str(ffprobe_path or os.getenv(FFPROBE_PATH_ENV, "")).strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise FFprobeError(f"ffprobe executable does not exist: {path}")
        return str(path)
    discovered = shutil.which("ffprobe")
    if discovered is None:
        raise FFprobeError(
            f"ffprobe was not found; configure {FFPROBE_PATH_ENV} or add it to PATH"
        )
    return discovered


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def probe_audio(
    path: str | Path,
    *,
    ffprobe_path: str | Path | None = None,
    timeout_sec: float = 30.0,
) -> AudioMetadata:
    if timeout_sec <= 0:
        raise ValueError("timeout_sec must be greater than zero")
    media_path = Path(path).expanduser().resolve()
    if not media_path.is_file():
        raise FFprobeError(f"Audio file does not exist: {media_path}")
    executable = _resolve_executable(ffprobe_path)
    command = [
        executable,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name,sample_rate,channels,duration",
        "-of",
        "json",
        str(media_path),
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
        raise FFprobeError(f"ffprobe timed out after {timeout_sec:g} seconds") from exc
    except OSError as exc:
        raise FFprobeError(f"Could not execute ffprobe: {exc}") from exc
    if result.returncode != 0:
        message = result.stderr.strip() or f"exit code {result.returncode}"
        raise FFprobeError(f"ffprobe failed for {media_path.name}: {message}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FFprobeError("ffprobe returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise FFprobeError("ffprobe JSON root must be an object")
    streams = payload.get("streams")
    if not isinstance(streams, list):
        streams = []
    audio_stream = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"),
        None,
    )
    if audio_stream is None:
        raise FFprobeError(f"No audio stream found in {media_path.name}")

    format_data = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    duration = _positive_float(format_data.get("duration")) or _positive_float(
        audio_stream.get("duration")
    )
    if duration is None:
        raise FFprobeError(f"Audio duration must be greater than zero: {media_path.name}")
    try:
        sample_rate = int(audio_stream.get("sample_rate"))
        channels = int(audio_stream.get("channels"))
    except (TypeError, ValueError) as exc:
        raise FFprobeError(f"Invalid audio stream metadata: {media_path.name}") from exc
    codec = str(audio_stream.get("codec_name") or "").strip()
    if sample_rate <= 0 or channels <= 0 or not codec:
        raise FFprobeError(f"Incomplete audio stream metadata: {media_path.name}")
    return AudioMetadata(
        duration_sec=duration,
        sample_rate=sample_rate,
        channels=channels,
        codec=codec,
    )
