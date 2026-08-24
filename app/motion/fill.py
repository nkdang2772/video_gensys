from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.media.ffmpeg import FFmpegError, run_ffmpeg
from app.media.ffprobe import VideoMetadata, probe_video
from app.motion.kenburns import render_kenburns

FILL_POLICIES = frozenset({"extend", "split", "loop"})
SAFE_SHOT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class SubShotPlan:
    shot_id: str
    index: int
    start_sec: float
    end_sec: float
    duration_sec: float


@dataclass(frozen=True, slots=True)
class MotionFillResult:
    policy: str
    output_path: Path | None
    source_duration_sec: float | None
    target_duration_sec: float
    subshots: tuple[SubShotPlan, ...] = ()


def plan_subshots(
    shot_id: str,
    effective_duration_sec: float,
    max_segment_duration_sec: float,
) -> tuple[SubShotPlan, ...]:
    if not SAFE_SHOT_ID.fullmatch(shot_id):
        raise ValueError(f"Unsafe shot_id for split: {shot_id!r}")
    duration = float(effective_duration_sec)
    segment = float(max_segment_duration_sec)
    if not math.isfinite(duration) or not math.isfinite(segment) or duration <= 0 or segment <= 0:
        raise ValueError("Split durations must be finite and greater than zero")
    count = max(1, math.ceil(duration / segment))
    equal_duration = duration / count
    plans = []
    for index in range(1, count + 1):
        start = (index - 1) * equal_duration
        end = duration if index == count else index * equal_duration
        plans.append(
            SubShotPlan(
                shot_id=f"{shot_id}_{index:02d}",
                index=index,
                start_sec=start,
                end_sec=end,
                duration_sec=end - start,
            )
        )
    return tuple(plans)


def _destination(path: str | Path) -> Path:
    destination = Path(path).expanduser().resolve()
    if destination.suffix.lower() != ".mp4":
        raise ValueError("Motion fill output_path must use the .mp4 extension")
    if destination.exists():
        raise ValueError(f"Motion fill output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _render_video(
    arguments: list[str],
    destination: Path,
    *,
    ffmpeg_path: str | Path | None,
    timeout_sec: float,
) -> Path:
    temporary = destination.with_name(f".{destination.stem}.{os.getpid()}.tmp.mp4")
    temporary.unlink(missing_ok=True)
    try:
        run_ffmpeg(["-y", *arguments, str(temporary)], ffmpeg_path=ffmpeg_path, timeout_sec=timeout_sec)
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)


def apply_fill_policy(
    clip_path: str | Path,
    target_duration_sec: float,
    policy: str = "extend",
    *,
    output_path: str | Path | None = None,
    shot_id: str = "shot",
    max_segment_duration_sec: float | None = None,
    ffmpeg_path: str | Path | None = None,
    ffprobe_path: str | Path | None = None,
    timeout_sec: float = 300.0,
) -> MotionFillResult:
    clean_policy = policy.strip().lower()
    if clean_policy not in FILL_POLICIES:
        raise ValueError(f"Unsupported motion fill policy: {policy}")
    target = float(target_duration_sec)
    if not math.isfinite(target) or target <= 0:
        raise ValueError("target_duration_sec must be finite and greater than zero")
    source = Path(clip_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"Motion clip does not exist: {source}")
    metadata = probe_video(source, ffprobe_path=ffprobe_path)
    if clean_policy == "split":
        max_duration = float(max_segment_duration_sec or metadata.duration_sec)
        return MotionFillResult(
            policy="split",
            output_path=None,
            source_duration_sec=metadata.duration_sec,
            target_duration_sec=target,
            subshots=plan_subshots(shot_id, target, max_duration),
        )
    destination = _destination(output_path or source.with_name(f"{source.stem}_{clean_policy}.mp4"))
    common = ["-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    try:
        if clean_policy == "loop" and target > metadata.duration_sec:
            _render_video(
                ["-stream_loop", "-1", "-i", str(source), "-t", f"{target:.6f}", *common],
                destination,
                ffmpeg_path=ffmpeg_path,
                timeout_sec=timeout_sec,
            )
        elif target <= metadata.duration_sec + (0.5 / metadata.frame_rate):
            _render_video(
                ["-i", str(source), "-t", f"{target:.6f}", *common],
                destination,
                ffmpeg_path=ffmpeg_path,
                timeout_sec=timeout_sec,
            )
        else:
            remaining = target - metadata.duration_sec
            workspace = destination.parent / f".{destination.stem}.{os.getpid()}.fill"
            workspace.mkdir(parents=True, exist_ok=False)
            frame = workspace / "last.png"
            tail = workspace / "tail.mp4"
            try:
                run_ffmpeg(
                    ["-y", "-sseof", "-0.1", "-i", str(source), "-frames:v", "1", str(frame)],
                    ffmpeg_path=ffmpeg_path,
                    timeout_sec=timeout_sec,
                )
                render_kenburns(
                    frame,
                    remaining,
                    "zoom_in",
                    1.0,
                    1.03,
                    output_path=tail,
                    fps=metadata.frame_rate,
                    width=metadata.width,
                    height=metadata.height,
                    ffmpeg_path=ffmpeg_path,
                    timeout_sec=timeout_sec,
                )
                frames = max(1, round(target * metadata.frame_rate))
                complex_filter = (
                    f"[0:v]fps={metadata.frame_rate:g},scale={metadata.width}:{metadata.height},"
                    "setsar=1,setpts=PTS-STARTPTS[v0];"
                    f"[1:v]fps={metadata.frame_rate:g},scale={metadata.width}:{metadata.height},"
                    "setsar=1,setpts=PTS-STARTPTS[v1];[v0][v1]concat=n=2:v=1:a=0[outv]"
                )
                _render_video(
                    [
                        "-i", str(source), "-i", str(tail), "-filter_complex", complex_filter,
                        "-map", "[outv]", "-frames:v", str(frames), *common,
                    ],
                    destination,
                    ffmpeg_path=ffmpeg_path,
                    timeout_sec=timeout_sec,
                )
            finally:
                frame.unlink(missing_ok=True)
                tail.unlink(missing_ok=True)
                workspace.rmdir()
    except (FFmpegError, OSError) as exc:
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"Motion fill failed: {exc}") from exc
    return MotionFillResult(
        policy=clean_policy,
        output_path=destination,
        source_duration_sec=metadata.duration_sec,
        target_duration_sec=target,
    )
