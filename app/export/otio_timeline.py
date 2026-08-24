from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import opentimelineio as otio


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    shot_id: str
    visual_path: Path | None
    visual_is_image: bool
    audio_path: Path | None
    duration_sec: float
    audio_duration_sec: float
    head_padding_sec: float = 0.0
    tail_padding_sec: float = 0.0
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class OtioExportResult:
    timeline_path: Path
    bundle_path: Path
    duration_sec: float
    transition_count: int


def _time(frames: int, fps: float) -> otio.opentime.RationalTime:
    return otio.opentime.RationalTime(frames, fps)


def _range(frames: int, fps: float) -> otio.opentime.TimeRange:
    return otio.opentime.TimeRange(_time(0, fps), _time(frames, fps))


def _frames(seconds: float, fps: float, *, minimum: int = 0) -> int:
    return max(minimum, round(seconds * fps))


def _validate_media(path: Path | None, label: str) -> Path | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"OTIO {label} media does not exist: {resolved}")
    return resolved


def _external_reference(path: Path, frames: int, fps: float) -> otio.schema.ExternalReference:
    return otio.schema.ExternalReference(
        target_url=path.as_uri(),
        available_range=_range(frames, fps),
    )


def export_otio_timeline(
    destination: str | Path,
    entries: list[TimelineEntry],
    *,
    fps: float,
    width: int,
    height: int,
    transition_duration_sec: float = 0.25,
    timeline_name: str = "Video GenSystem Timeline",
) -> OtioExportResult:
    rate = float(fps)
    transition_seconds = float(transition_duration_sec)
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("OTIO timeline FPS must be finite and greater than zero")
    if width <= 0 or height <= 0:
        raise ValueError("OTIO timeline resolution must be greater than zero")
    if (
        not math.isfinite(transition_seconds)
        or transition_seconds < 0
        or transition_seconds > 5
    ):
        raise ValueError("OTIO transition duration must be between 0 and 5 seconds")
    if not entries:
        raise ValueError("OTIO timeline requires at least one shot")

    folder = Path(destination).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    timeline_path = folder / "timeline.otio"
    bundle_path = folder / "timeline.otioz"
    if timeline_path.exists() or bundle_path.exists():
        raise FileExistsError("OTIO timeline output already exists")

    timeline = otio.schema.Timeline(name=timeline_name)
    timeline.global_start_time = _time(0, rate)
    timeline.metadata["video_gensystem"] = {
        "fps": rate,
        "width": width,
        "height": height,
        "transition": "SMPTE_Dissolve" if transition_seconds else "cut",
        "transition_duration_sec": transition_seconds,
    }
    video_track = otio.schema.Track(name="V1 Visual", kind=otio.schema.TrackKind.Video)
    audio_track = otio.schema.Track(name="A1 Voice", kind=otio.schema.TrackKind.Audio)
    timeline.tracks.extend([video_track, audio_track])

    previous_visual_frames: int | None = None
    transition_count = 0
    total_frames = 0
    desired_transition_frames = _frames(transition_seconds, rate)
    try:
        for entry in entries:
            duration = float(entry.duration_sec)
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError(f"OTIO shot {entry.shot_id} has an invalid duration")
            duration_frames = _frames(duration, rate, minimum=1)
            visual_path = _validate_media(entry.visual_path, "visual")
            audio_path = _validate_media(entry.audio_path, "audio")
            metadata = {"video_gensystem": {"shot_id": entry.shot_id, **(entry.metadata or {})}}

            if visual_path is None:
                visual_item: otio.core.Item = otio.schema.Gap(
                    name=f"{entry.shot_id} missing visual",
                    source_range=_range(duration_frames, rate),
                    metadata=metadata,
                )
            else:
                visual_item = otio.schema.Clip(
                    name=entry.shot_id,
                    media_reference=_external_reference(visual_path, duration_frames, rate),
                    source_range=_range(duration_frames, rate),
                    metadata=metadata,
                )
                if entry.visual_is_image:
                    visual_item.effects.append(otio.schema.FreezeFrame(name="Still image"))

            current_has_visual = visual_path is not None
            if (
                desired_transition_frames > 0
                and previous_visual_frames is not None
                and current_has_visual
            ):
                transition_frames = min(
                    desired_transition_frames,
                    previous_visual_frames,
                    duration_frames,
                )
                if transition_frames > 0:
                    in_frames = transition_frames // 2
                    out_frames = transition_frames - in_frames
                    video_track.append(
                        otio.schema.Transition(
                            name="Cross Dissolve",
                            transition_type=otio.schema.TransitionTypes.SMPTE_Dissolve,
                            in_offset=_time(in_frames, rate),
                            out_offset=_time(out_frames, rate),
                            metadata={"video_gensystem": {"editable": True}},
                        )
                    )
                    transition_count += 1
            video_track.append(visual_item)
            previous_visual_frames = duration_frames if current_has_visual else None

            if audio_path is None:
                audio_track.append(
                    otio.schema.Gap(
                        name=f"{entry.shot_id} missing voice",
                        source_range=_range(duration_frames, rate),
                        metadata=metadata,
                    )
                )
            else:
                head_frames = min(
                    duration_frames,
                    _frames(max(0.0, float(entry.head_padding_sec)), rate),
                )
                remaining = duration_frames - head_frames
                voice_frames = min(
                    remaining,
                    _frames(max(0.0, float(entry.audio_duration_sec)), rate),
                )
                tail_frames = duration_frames - head_frames - voice_frames
                if head_frames:
                    audio_track.append(
                        otio.schema.Gap(
                            name=f"{entry.shot_id} head padding",
                            source_range=_range(head_frames, rate),
                        )
                    )
                if voice_frames:
                    audio_track.append(
                        otio.schema.Clip(
                            name=f"{entry.shot_id} voice",
                            media_reference=_external_reference(audio_path, voice_frames, rate),
                            source_range=_range(voice_frames, rate),
                            metadata=metadata,
                        )
                    )
                if tail_frames:
                    audio_track.append(
                        otio.schema.Gap(
                            name=f"{entry.shot_id} tail padding",
                            source_range=_range(tail_frames, rate),
                        )
                    )
            total_frames += duration_frames

        otio.adapters.write_to_file(timeline, str(timeline_path), adapter_name="otio_json")
        otio.adapters.write_to_file(timeline, str(bundle_path), adapter_name="otioz")
    except Exception:
        timeline_path.unlink(missing_ok=True)
        bundle_path.unlink(missing_ok=True)
        raise

    return OtioExportResult(
        timeline_path=timeline_path,
        bundle_path=bundle_path,
        duration_sec=total_frames / rate,
        transition_count=transition_count,
    )
