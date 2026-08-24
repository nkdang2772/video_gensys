from __future__ import annotations

import math
import os
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.media.ffmpeg import FFmpegError, run_ffmpeg

KEN_BURNS_DIRECTIONS = frozenset(
    {"center", "zoom_in", "zoom_out", "left_to_right", "right_to_left", "top_to_bottom", "bottom_to_top"}
)


class KenBurnsError(RuntimeError):
    pass


def _number(value: float, name: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite")
    return parsed


def _pan_expressions(direction: str, frames: int) -> tuple[str, str]:
    last = max(1, frames - 1)
    center_x = "iw/2-(iw/zoom/2)"
    center_y = "ih/2-(ih/zoom/2)"
    if direction == "left_to_right":
        return f"(iw-iw/zoom)*on/{last}", center_y
    if direction == "right_to_left":
        return f"(iw-iw/zoom)*(1-on/{last})", center_y
    if direction == "top_to_bottom":
        return center_x, f"(ih-ih/zoom)*on/{last}"
    if direction == "bottom_to_top":
        return center_x, f"(ih-ih/zoom)*(1-on/{last})"
    return center_x, center_y


def render_kenburns(
    image_path: str | Path,
    duration: float,
    direction: str = "zoom_in",
    zoom_start: float = 1.0,
    zoom_end: float = 1.08,
    *,
    output_path: str | Path | None = None,
    fps: float = 30.0,
    width: int | None = None,
    height: int | None = None,
    ffmpeg_path: str | Path | None = None,
    timeout_sec: float = 300.0,
) -> Path:
    source = Path(image_path).expanduser().resolve()
    if not source.is_file():
        raise KenBurnsError(f"Ken Burns source image does not exist: {source}")
    clean_direction = direction.strip().lower()
    if clean_direction not in KEN_BURNS_DIRECTIONS:
        raise ValueError(f"Unsupported Ken Burns direction: {direction}")
    duration_value = _number(duration, "duration")
    fps_value = _number(fps, "fps")
    start = _number(zoom_start, "zoom_start")
    end = _number(zoom_end, "zoom_end")
    if duration_value <= 0 or fps_value <= 0:
        raise ValueError("duration and fps must be greater than zero")
    if start < 1.0 or end < 1.0 or start > 4.0 or end > 4.0:
        raise ValueError("zoom values must be between 1.0 and 4.0")
    if clean_direction == "zoom_out" and zoom_start == 1.0 and zoom_end == 1.08:
        start, end = end, start
    try:
        with Image.open(source) as image:
            source_width, source_height = image.size
    except (OSError, UnidentifiedImageError) as exc:
        raise KenBurnsError(f"Invalid Ken Burns source image: {source}") from exc
    target_width = int(width or source_width)
    target_height = int(height or source_height)
    target_width -= target_width % 2
    target_height -= target_height % 2
    if target_width < 2 or target_height < 2:
        raise ValueError("Ken Burns output dimensions must be at least 2x2")
    destination = Path(output_path).expanduser().resolve() if output_path else source.with_name(
        f"{source.stem}_kenburns.mp4"
    )
    if destination.suffix.lower() != ".mp4":
        raise ValueError("Ken Burns output_path must use the .mp4 extension")
    if destination.exists():
        raise KenBurnsError(f"Ken Burns output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, round(duration_value * fps_value))
    last = max(1, frames - 1)
    zoom = f"{start:.8f}+({end - start:.8f})*on/{last}"
    x_expr, y_expr = _pan_expressions(clean_direction, frames)
    video_filter = (
        f"scale={target_width}:{target_height}:force_original_aspect_ratio=increase,"
        f"crop={target_width}:{target_height},"
        f"zoompan=z='{zoom}':x='{x_expr}':y='{y_expr}':d={frames}:"
        f"s={target_width}x{target_height}:fps={fps_value:g},format=yuv420p"
    )
    temporary = destination.with_name(f".{destination.stem}.{os.getpid()}.tmp.mp4")
    temporary.unlink(missing_ok=True)
    try:
        run_ffmpeg(
            [
                "-y", "-loop", "1", "-i", str(source), "-vf", video_filter,
                "-frames:v", str(frames), "-an", "-c:v", "libx264", "-preset", "medium",
                "-crf", "18", "-movflags", "+faststart", str(temporary),
            ],
            ffmpeg_path=ffmpeg_path,
            timeout_sec=timeout_sec,
        )
        temporary.replace(destination)
    except (FFmpegError, OSError) as exc:
        raise KenBurnsError(str(exc)) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return destination
