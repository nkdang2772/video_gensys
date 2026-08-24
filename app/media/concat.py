from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.media.ffmpeg import run_ffmpeg
from app.media.ffprobe import probe_audio, probe_video
from app.models import Asset, Episode, Scene, Shot
from app.paths import resolve


@dataclass(frozen=True, slots=True)
class PreviewResult:
    output_path: Path
    shot_count: int
    placeholder_shot_ids: tuple[str, ...]
    duration_sec: float


def _chosen(shot: Shot, asset_type: str) -> Asset | None:
    return next(
        (asset for asset in shot.assets if asset.asset_type == asset_type and asset.is_chosen),
        None,
    )


def _duration(shot: Shot, visual: Asset | None, audio: Asset | None) -> float:
    duration = (
        float(shot.audio_duration_sec or 0)
        + float(shot.head_padding_sec or 0)
        + float(shot.tail_padding_sec or 0)
    )
    if duration <= 0 and audio is not None:
        duration = float(audio.duration_sec or 0)
    if duration <= 0 and visual is not None:
        duration = float(visual.duration_sec or 0)
    return duration if duration > 0 else 3.0


def _placeholder(path: Path, shot_id: str, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, (185, 15, 25))
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", max(36, size[1] // 10))
    except OSError:
        font = ImageFont.load_default()
    label = f"MISSING ASSET\n{shot_id}"
    box = draw.multiline_textbbox((0, 0), label, font=font, align="center", spacing=12)
    x = (size[0] - (box[2] - box[0])) / 2
    y = (size[1] - (box[3] - box[1])) / 2
    draw.multiline_text((x, y), label, fill="white", font=font, align="center", spacing=12)
    image.save(path, format="PNG")


def render_shot_preview(
    episode: Episode,
    shot: Shot,
    *,
    output_path: str | Path | None = None,
    width: int = 1280,
    height: int = 720,
    ffmpeg_path: str | Path | None = None,
    ffprobe_path: str | Path | None = None,
    force: bool = False,
) -> PreviewResult:
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("Preview dimensions must be positive even integers")
    fps = float(episode.effective_fps)
    if fps <= 0:
        raise ValueError("Episode FPS must be greater than zero")
    destination = Path(output_path).expanduser().resolve() if output_path else resolve(
        episode, f"proxies/shots/{shot.shot_id}_preview.mp4"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)

    motion = _chosen(shot, "video")
    image = _chosen(shot, "image")
    audio = _chosen(shot, "audio")
    visual = motion or image
    placeholder_ids: tuple[str, ...] = ()
    if visual is None:
        visual_path = destination.parent / f"{shot.shot_id}_placeholder.png"
        _placeholder(visual_path, shot.shot_id, (width, height))
        visual_is_image = True
        placeholder_ids = (shot.shot_id,)
    else:
        visual_path = resolve(episode, visual.file_path)
        if not visual_path.is_file():
            visual_path = destination.parent / f"{shot.shot_id}_placeholder.png"
            _placeholder(visual_path, shot.shot_id, (width, height))
            visual_is_image = True
            placeholder_ids = (shot.shot_id,)
        else:
            visual_is_image = visual.asset_type == "image"
    audio_path = resolve(episode, audio.file_path) if audio is not None else None
    if audio_path is not None and not audio_path.is_file():
        audio_path = None
    duration = _duration(shot, visual, audio)
    if destination.exists() and not force:
        metadata = probe_video(destination, ffprobe_path=ffprobe_path)
        return PreviewResult(destination, 1, placeholder_ids, metadata.duration_sec)
    temporary = destination.with_name(f".{destination.stem}.tmp{destination.suffix}")
    temporary.unlink(missing_ok=True)

    arguments: list[str] = ["-y"]
    if visual_is_image:
        arguments.extend(["-loop", "1", "-i", str(visual_path)])
    else:
        arguments.extend(["-i", str(visual_path)])
    if audio_path is not None:
        arguments.extend(["-i", str(audio_path)])
    else:
        arguments.extend(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"])
    delay_ms = max(0, round(float(shot.head_padding_sec or 0) * 1000))
    video_filter = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,fps={fps:g},"
        f"tpad=stop_mode=clone:stop_duration={duration:g},trim=duration={duration:g},"
        "setpts=PTS-STARTPTS[v]"
    )
    audio_filter = (
        f"[1:a]adelay={delay_ms}:all=1,apad,atrim=duration={duration:g},"
        "asetpts=PTS-STARTPTS[a]"
    )
    arguments.extend(
        [
            "-filter_complex",
            f"{video_filter};{audio_filter}",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            f"{duration:g}",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(temporary),
        ]
    )
    try:
        run_ffmpeg(arguments, ffmpeg_path=ffmpeg_path)
        metadata = probe_video(temporary, ffprobe_path=ffprobe_path)
        if audio_path is not None:
            probe_audio(temporary, ffprobe_path=ffprobe_path)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return PreviewResult(destination, 1, placeholder_ids, metadata.duration_sec)


def concat_previews(
    inputs: list[Path],
    output_path: str | Path,
    *,
    ffmpeg_path: str | Path | None = None,
    ffprobe_path: str | Path | None = None,
    force: bool = False,
) -> Path:
    if not inputs:
        raise ValueError("At least one shot preview is required")
    for source in inputs:
        if not source.is_file():
            raise FileNotFoundError(source)
    destination = Path(output_path).expanduser().resolve()
    if destination.exists() and not force:
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}.tmp{destination.suffix}")
    temporary.unlink(missing_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".ffconcat", delete=False, dir=destination.parent
    ) as handle:
        list_path = Path(handle.name)
        handle.write("ffconcat version 1.0\n")
        for source in inputs:
            safe = source.resolve().as_posix().replace("'", "'\\''")
            handle.write(f"file '{safe}'\n")
    try:
        run_ffmpeg(
            ["-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", "-movflags", "+faststart", str(temporary)],
            ffmpeg_path=ffmpeg_path,
        )
        probe_video(temporary, ffprobe_path=ffprobe_path)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        list_path.unlink(missing_ok=True)
    return destination


def render_sequence_preview(
    session: Session,
    episode_id: int,
    *,
    scene_id: int | None = None,
    ffmpeg_path: str | Path | None = None,
    ffprobe_path: str | Path | None = None,
    force: bool = False,
) -> PreviewResult:
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise ValueError(f"Episode not found: {episode_id}")
    query = select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.order_index, Shot.id)
    if scene_id is not None:
        scene = session.get(Scene, scene_id)
        if scene is None or scene.episode_id != episode_id:
            raise ValueError(f"Scene not found in Episode: {scene_id}")
        query = query.where(Shot.scene_id == scene_id)
        output = resolve(episode, f"proxies/scene_{scene.scene_number:03d}_preview.mp4")
    else:
        output = resolve(episode, "proxies/full_preview_720p.mp4")
    shots = list(session.scalars(query))
    if not shots:
        raise ValueError("The selected preview contains no shots")
    if output.exists() and not force:
        placeholder_ids = tuple(
            shot.shot_id
            for shot in shots
            if not any(
                asset.is_chosen
                and asset.asset_type in {"image", "video"}
                and resolve(episode, asset.file_path).is_file()
                for asset in shot.assets
            )
        )
        metadata = probe_video(output, ffprobe_path=ffprobe_path)
        return PreviewResult(output, len(shots), placeholder_ids, metadata.duration_sec)
    paths: list[Path] = []
    placeholders: list[str] = []
    for shot in shots:
        result = render_shot_preview(
            episode,
            shot,
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
            force=force,
        )
        paths.append(result.output_path)
        placeholders.extend(result.placeholder_shot_ids)
    if len(paths) == 1:
        if output.exists() and not force:
            raise FileExistsError(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(paths[0], output)
    else:
        concat_previews(
            paths,
            output,
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
            force=force,
        )
    metadata = probe_video(output, ffprobe_path=ffprobe_path)
    return PreviewResult(output, len(shots), tuple(placeholders), metadata.duration_sec)
