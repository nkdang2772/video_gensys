from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter, UnidentifiedImageError

from app.media.ffmpeg import FFmpegError, run_ffmpeg


class SpriteParallaxError(RuntimeError):
    pass


def _finite_positive(value: float, name: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{name} must be a finite number greater than zero")
    return parsed


def render_sprite_parallax(
    image_path: str | Path,
    duration: float,
    subject_box: tuple[int, int, int, int],
    *,
    output_path: str | Path,
    fps: float = 30.0,
    sway_px: float = 3.0,
    breathe_px: float = 4.0,
    period_sec: float = 2.2,
    feather_px: float = 14.0,
    ffmpeg_path: str | Path | None = None,
) -> Path:
    source = Path(image_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    duration_value = _finite_positive(duration, "duration")
    fps_value = _finite_positive(fps, "fps")
    period_value = _finite_positive(period_sec, "period_sec")
    destination = Path(output_path).expanduser().resolve()
    if destination.suffix.lower() != ".mp4":
        raise ValueError("output_path must use the .mp4 extension")
    if destination.exists():
        raise FileExistsError(destination)
    try:
        with Image.open(source) as opened:
            base = opened.convert("RGBA")
    except (OSError, UnidentifiedImageError) as exc:
        raise SpriteParallaxError(f"Invalid sprite source image: {source}") from exc
    left, top, right, bottom = (int(value) for value in subject_box)
    if left < 0 or top < 0 or right <= left or bottom <= top or right > base.width or bottom > base.height:
        raise ValueError("subject_box must be inside the source image")
    if not math.isfinite(float(sway_px)) or not math.isfinite(float(breathe_px)):
        raise ValueError("sprite motion values must be finite")
    feather = max(0.0, float(feather_px))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}.{os.getpid()}.tmp.mp4")
    temporary.unlink(missing_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="sprite-parallax-", dir=destination.parent) as temp_name:
            temp = Path(temp_name)
            sprite_path = temp / "sprite.png"
            sprite = base.crop((left, top, right, bottom))
            mask = Image.new("L", sprite.size, 255)
            if feather:
                edge = max(1, round(feather * 2))
                inner = Image.new("L", (max(1, sprite.width - edge * 2), max(1, sprite.height - edge * 2)), 255)
                mask = Image.new("L", sprite.size, 0)
                mask.paste(inner, (edge, edge))
                mask = mask.filter(ImageFilter.GaussianBlur(feather))
            sprite.putalpha(mask)
            sprite.save(sprite_path, format="PNG")
            omega = 2 * math.pi / period_value
            x_expr = f"{left}+{float(sway_px):g}*sin({omega:.8f}*t)"
            y_expr = f"{top}-{float(breathe_px):g}*(1-cos({omega:.8f}*t))/2"
            filters = (
                f"[0:v]fps={fps_value:g},setpts=PTS-STARTPTS[base];"
                f"[1:v]format=rgba[subject];"
                f"[base][subject]overlay=x='{x_expr}':y='{y_expr}':eval=frame,format=yuv420p[v]"
            )
            run_ffmpeg(
                [
                    "-y", "-loop", "1", "-i", str(source), "-loop", "1", "-i", str(sprite_path),
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-filter_complex", filters, "-map", "[v]", "-map", "2:a",
                    "-t", f"{duration_value:g}", "-r", f"{fps_value:g}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-ar", "48000", "-ac", "2", "-shortest", "-movflags", "+faststart",
                    str(temporary),
                ],
                ffmpeg_path=ffmpeg_path,
            )
        temporary.replace(destination)
    except (FFmpegError, OSError) as exc:
        raise SpriteParallaxError(str(exc)) from exc
    finally:
        temporary.unlink(missing_ok=True)
    return destination
