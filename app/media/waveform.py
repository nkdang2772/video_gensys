from __future__ import annotations

import os
import tempfile
import wave
from pathlib import Path

import numpy as np


class WaveformError(RuntimeError):
    pass


def decode_pcm_frames(raw_frames: bytes, sample_width: int, channels: int) -> np.ndarray:
    if channels <= 0:
        raise WaveformError("WAV channel count must be positive")
    if sample_width == 1:
        samples = np.frombuffer(raw_frames, dtype=np.uint8).astype(np.int16) - 128
    elif sample_width == 2:
        samples = np.frombuffer(raw_frames, dtype="<i2").astype(np.int32)
    elif sample_width == 3:
        raw = np.frombuffer(raw_frames, dtype=np.uint8)
        if len(raw) % 3:
            raise WaveformError("Invalid 24-bit PCM frame data")
        triples = raw.reshape(-1, 3).astype(np.int32)
        samples = triples[:, 0] | (triples[:, 1] << 8) | (triples[:, 2] << 16)
        samples = np.where(samples & 0x800000, samples - 0x1000000, samples)
    elif sample_width == 4:
        samples = np.frombuffer(raw_frames, dtype="<i4").astype(np.int64)
    else:
        raise WaveformError(f"Unsupported PCM sample width: {sample_width} bytes")
    if len(samples) % channels:
        raise WaveformError("PCM sample count is not divisible by channel count")
    return samples.reshape(-1, channels)


def read_pcm_wav(path: str | Path) -> tuple[np.ndarray, int, int]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise WaveformError(f"WAV file does not exist: {source}")
    try:
        with wave.open(str(source), "rb") as wav_file:
            if wav_file.getcomptype() != "NONE":
                raise WaveformError("Only uncompressed PCM WAV is supported")
            channels = wav_file.getnchannels()
            sample_rate = wav_file.getframerate()
            sample_width = wav_file.getsampwidth()
            frames = wav_file.readframes(wav_file.getnframes())
    except (wave.Error, EOFError, OSError) as exc:
        raise WaveformError(f"Could not read WAV: {exc}") from exc
    if sample_rate <= 0:
        raise WaveformError("WAV sample rate must be positive")
    return decode_pcm_frames(frames, sample_width, channels), sample_rate, sample_width


def generate_waveform_png(
    source_path: str | Path,
    output_path: str | Path,
    *,
    max_points: int = 4000,
    width_px: int = 1600,
    height_px: int = 300,
    overwrite: bool = False,
) -> Path:
    if max_points <= 0 or width_px <= 0 or height_px <= 0:
        raise ValueError("Waveform dimensions and max_points must be positive")
    source = Path(source_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    if output.suffix.lower() != ".png":
        raise ValueError("Waveform output must use the .png extension")
    if output == source:
        raise WaveformError("Waveform output may not overwrite the source WAV")
    if output.exists() and not overwrite:
        raise FileExistsError(f"Waveform output already exists: {output}")

    samples, sample_rate, sample_width = read_pcm_wav(source)
    if samples.size == 0:
        raise WaveformError("Cannot render an empty WAV")
    mono = samples.astype(np.float64).mean(axis=1)
    full_scale = float(2 ** (sample_width * 8 - 1))
    mono = np.clip(mono / full_scale, -1.0, 1.0)
    step = max(1, int(np.ceil(len(mono) / max_points)))
    sampled = mono[::step]
    times = np.arange(len(sampled), dtype=np.float64) * step / sample_rate

    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    output.parent.mkdir(parents=True, exist_ok=True)
    dpi = 100
    figure, axis = plt.subplots(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
    figure.patch.set_facecolor("#111827")
    axis.set_facecolor("#111827")
    axis.plot(times, sampled, color="#38bdf8", linewidth=0.7)
    axis.fill_between(times, sampled, 0, color="#0ea5e9", alpha=0.35)
    axis.set_xlim(0, max(times[-1], 1 / sample_rate))
    axis.set_ylim(-1.05, 1.05)
    axis.axis("off")
    figure.tight_layout(pad=0)

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output.stem}-", suffix=".png", dir=output.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        figure.savefig(temporary_path, format="png", dpi=dpi, facecolor=figure.get_facecolor())
        if output.exists() and not overwrite:
            raise FileExistsError(f"Waveform output already exists: {output}")
        os.replace(temporary_path, output)
        temporary_path = None
    finally:
        plt.close(figure)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return output

