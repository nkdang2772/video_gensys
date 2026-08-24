from __future__ import annotations

import math
import os
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from app.media.waveform import WaveformError, decode_pcm_frames


class AudioCutterError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SegmentSpec:
    start_sec: float
    end_sec: float


@dataclass(frozen=True, slots=True)
class WavSegment:
    path: Path
    start_sec: float
    end_sec: float
    duration_sec: float


@dataclass(frozen=True, slots=True)
class SilenceInterval:
    start_sec: float
    end_sec: float


def _normalize_segments(
    segments: Sequence[SegmentSpec | tuple[float, float]], duration_sec: float
) -> list[SegmentSpec]:
    normalized: list[SegmentSpec] = []
    previous_end = 0.0
    for index, segment in enumerate(segments, start=1):
        spec = segment if isinstance(segment, SegmentSpec) else SegmentSpec(*segment)
        if not math.isfinite(spec.start_sec) or not math.isfinite(spec.end_sec):
            raise ValueError(f"Segment {index} timestamps must be finite")
        if spec.start_sec < 0 or spec.end_sec <= spec.start_sec:
            raise ValueError(f"Segment {index} has invalid timestamps")
        if spec.end_sec > duration_sec + 1e-9:
            raise ValueError(f"Segment {index} exceeds source duration")
        if spec.start_sec < previous_end - 1e-9:
            raise ValueError("Segments must be ordered and may not overlap")
        normalized.append(spec)
        previous_end = spec.end_sec
    if not normalized:
        raise ValueError("At least one segment is required")
    return normalized


def cut_wav(
    source_path: str | Path,
    segments: Sequence[SegmentSpec | tuple[float, float]],
    output_dir: str | Path,
    *,
    prefix: str | None = None,
    overwrite: bool = False,
) -> list[WavSegment]:
    source = Path(source_path).expanduser().resolve()
    destination_dir = Path(output_dir).expanduser().resolve()
    if not source.is_file():
        raise AudioCutterError(f"Source WAV does not exist: {source}")
    try:
        with wave.open(str(source), "rb") as input_wav:
            if input_wav.getcomptype() != "NONE":
                raise AudioCutterError("Only uncompressed PCM WAV is supported")
            params = input_wav.getparams()
            sample_rate = input_wav.getframerate()
            total_frames = input_wav.getnframes()
    except (wave.Error, EOFError, OSError) as exc:
        raise AudioCutterError(f"Could not read source WAV: {exc}") from exc
    if sample_rate <= 0:
        raise AudioCutterError("Source WAV sample rate must be positive")
    duration_sec = total_frames / sample_rate
    specs = _normalize_segments(segments, duration_sec)
    destination_dir.mkdir(parents=True, exist_ok=True)
    clean_prefix = prefix or source.stem
    if not clean_prefix or any(character in clean_prefix for character in '<>:"/\\|?*'):
        raise ValueError("Segment prefix is not a safe filename component")

    planned: list[tuple[SegmentSpec, int, int, Path]] = []
    for index, spec in enumerate(specs, start=1):
        start_frame = round(spec.start_sec * sample_rate)
        end_frame = round(spec.end_sec * sample_rate)
        if end_frame <= start_frame:
            raise ValueError(f"Segment {index} is shorter than one audio frame")
        output = destination_dir / f"{clean_prefix}_segment_{index:03d}.wav"
        if output.resolve() == source:
            raise AudioCutterError("A segment may not overwrite the source WAV")
        if output.exists() and not overwrite:
            raise FileExistsError(f"Segment output already exists: {output}")
        planned.append((spec, start_frame, end_frame, output))

    created: list[Path] = []
    results: list[WavSegment] = []
    try:
        for spec, start_frame, end_frame, output in planned:
            with wave.open(str(source), "rb") as input_wav:
                input_wav.setpos(start_frame)
                frames = input_wav.readframes(end_frame - start_frame)
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    prefix=f".{output.stem}-", suffix=".wav", dir=destination_dir, delete=False
                ) as temporary:
                    temporary_path = Path(temporary.name)
                with wave.open(str(temporary_path), "wb") as output_wav:
                    output_wav.setparams(params)
                    output_wav.writeframes(frames)
                if output.exists() and not overwrite:
                    raise FileExistsError(f"Segment output already exists: {output}")
                os.replace(temporary_path, output)
                temporary_path = None
                created.append(output)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)
            actual_duration = (end_frame - start_frame) / sample_rate
            results.append(
                WavSegment(
                    path=output,
                    start_sec=start_frame / sample_rate,
                    end_sec=end_frame / sample_rate,
                    duration_sec=actual_duration,
                )
            )
        return results
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise


def detect_silence(
    source_path: str | Path,
    *,
    min_silence_sec: float = 0.5,
    threshold_dbfs: float = -40.0,
    window_sec: float = 0.05,
) -> list[SilenceInterval]:
    if min_silence_sec <= 0 or window_sec <= 0:
        raise ValueError("Silence durations must be positive")
    source = Path(source_path).expanduser().resolve()
    try:
        with wave.open(str(source), "rb") as wav_file:
            if wav_file.getcomptype() != "NONE":
                raise AudioCutterError("Only uncompressed PCM WAV is supported")
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            raw_frames = wav_file.readframes(wav_file.getnframes())
    except (wave.Error, EOFError, OSError) as exc:
        raise AudioCutterError(f"Could not read source WAV: {exc}") from exc
    try:
        samples = decode_pcm_frames(raw_frames, sample_width, channels)
    except WaveformError as exc:
        raise AudioCutterError(str(exc)) from exc
    if len(samples) == 0:
        return []
    mono = samples.astype(np.float64).mean(axis=1)
    full_scale = float(2 ** (sample_width * 8 - 1))
    threshold = full_scale * (10 ** (threshold_dbfs / 20.0))
    window_frames = max(1, round(window_sec * sample_rate))
    silent_windows: list[tuple[int, int]] = []
    for start in range(0, len(mono), window_frames):
        end = min(start + window_frames, len(mono))
        window = mono[start:end]
        rms = float(np.sqrt(np.mean(np.square(window)))) if len(window) else 0.0
        if rms <= threshold:
            silent_windows.append((start, end))

    intervals: list[SilenceInterval] = []
    if not silent_windows:
        return intervals
    group_start, group_end = silent_windows[0]
    for start, end in silent_windows[1:]:
        if start == group_end:
            group_end = end
            continue
        if (group_end - group_start) / sample_rate >= min_silence_sec:
            intervals.append(SilenceInterval(group_start / sample_rate, group_end / sample_rate))
        group_start, group_end = start, end
    if (group_end - group_start) / sample_rate >= min_silence_sec:
        intervals.append(SilenceInterval(group_start / sample_rate, group_end / sample_rate))
    return intervals

