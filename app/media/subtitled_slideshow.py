from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

from app.media.concat import concat_previews
from app.media.ffmpeg import FFmpegError, run_ffmpeg
from app.media.ffprobe import probe_video


class SubtitledSlideshowError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SubtitleSlide:
    image_path: Path
    duration_sec: float
    text: str
    speaker: str | None = None


@dataclass(frozen=True, slots=True)
class SubtitledSlideshowResult:
    output_path: Path
    slide_count: int
    duration_sec: float


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path("C:/Windows/Fonts/segoeui.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = " ".join(text.split()).split(" ")
    if not words or words == [""]:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        box = draw.textbbox((0, 0), candidate, font=font)
        if box[2] - box[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _frame(slide: SubtitleSlide, destination: Path, size: tuple[int, int]) -> None:
    try:
        with Image.open(slide.image_path) as source:
            image = source.convert("RGB")
    except (OSError, UnidentifiedImageError) as exc:
        raise SubtitledSlideshowError(f"Invalid slide image: {slide.image_path}") from exc
    width, height = size
    scale = max(width / image.width, height / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    frame = resized.crop((left, top, left + width, top + height)).convert("RGBA")
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(max(28, height // 22))
    label_font = _font(max(22, height // 29))
    lines = _wrap(draw, slide.text, font, width - 120)
    if not lines:
        raise ValueError("Subtitle text may not be empty")
    line_height = max(36, font.size + 10) if hasattr(font, "size") else 42
    label_height = 38 if slide.speaker else 0
    band_height = max(120, 36 + label_height + line_height * len(lines))
    band_top = height - band_height
    draw.rectangle((0, band_top, width, height), fill=(0, 0, 0, 190))
    y = band_top + 18
    if slide.speaker:
        label = slide.speaker.strip().upper()
        box = draw.textbbox((0, 0), label, font=label_font)
        draw.text(((width - (box[2] - box[0])) / 2, y), label, font=label_font, fill=(255, 199, 78, 255))
        y += label_height
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font)
        draw.text(
            ((width - (box[2] - box[0])) / 2, y), line, font=font,
            fill="white", stroke_width=2, stroke_fill=(0, 0, 0, 255),
        )
        y += line_height
    Image.alpha_composite(frame, overlay).convert("RGB").save(destination, format="PNG")


def render_subtitled_slideshow(
    slides: list[SubtitleSlide],
    output_path: str | Path,
    *,
    width: int = 1280,
    height: int = 720,
    fps: float = 30.0,
    ffmpeg_path: str | Path | None = None,
    ffprobe_path: str | Path | None = None,
    force: bool = False,
) -> SubtitledSlideshowResult:
    if not slides:
        raise ValueError("At least one subtitle slide is required")
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("Output dimensions must be positive even integers")
    if fps <= 0:
        raise ValueError("fps must be greater than zero")
    destination = Path(output_path).expanduser().resolve()
    if destination.suffix.lower() != ".mp4":
        raise ValueError("output_path must use the .mp4 extension")
    if destination.exists() and not force:
        raise FileExistsError(destination)
    for slide in slides:
        if not slide.image_path.is_file():
            raise FileNotFoundError(slide.image_path)
        if slide.duration_sec <= 0:
            raise ValueError("Slide duration must be greater than zero")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="subtitled-slideshow-", dir=destination.parent) as temp_name:
            temp = Path(temp_name)
            clips: list[Path] = []
            for index, slide in enumerate(slides, start=1):
                frame = temp / f"slide_{index:03d}.png"
                clip = temp / f"slide_{index:03d}.mp4"
                _frame(slide, frame, (width, height))
                run_ffmpeg(
                    [
                        "-y", "-loop", "1", "-i", str(frame),
                        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                        "-t", f"{slide.duration_sec:g}", "-r", f"{fps:g}",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", "-ac", "2",
                        "-shortest", "-movflags", "+faststart", str(clip),
                    ],
                    ffmpeg_path=ffmpeg_path,
                )
                clips.append(clip)
            concat_previews(
                clips, destination, ffmpeg_path=ffmpeg_path,
                ffprobe_path=ffprobe_path, force=True,
            )
        metadata = probe_video(destination, ffprobe_path=ffprobe_path)
    except (FFmpegError, OSError):
        destination.unlink(missing_ok=True)
        raise
    return SubtitledSlideshowResult(destination, len(slides), metadata.duration_sec)
