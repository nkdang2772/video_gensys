from __future__ import annotations

import hashlib
import math
import wave
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.media.audio_cutter import cut_wav, detect_silence
from app.media.waveform import generate_waveform_png


def write_pcm(path: Path, samples: np.ndarray, sample_rate: int = 8000) -> None:
    samples = np.asarray(samples, dtype="<i2")
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(samples.tobytes())


def test_generate_waveform_png_without_modifying_source(tmp_path: Path) -> None:
    sample_rate = 8000
    time = np.arange(sample_rate * 2) / sample_rate
    samples = (np.sin(2 * math.pi * 220 * time) * 12000).astype(np.int16)
    source = tmp_path / "tone.wav"
    output = tmp_path / "waveform.png"
    write_pcm(source, samples, sample_rate)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    result = generate_waveform_png(source, output, width_px=800, height_px=200)
    assert result == output.resolve()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    with Image.open(output) as image:
        assert image.format == "PNG"
        assert image.size == (800, 200)


def test_cut_five_minute_wav_into_ten_segments_with_low_drift(tmp_path: Path) -> None:
    sample_rate = 8000
    source = tmp_path / "five_minutes.wav"
    write_pcm(source, np.zeros(sample_rate * 300, dtype=np.int16), sample_rate)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    specs = [(index * 30.0, (index + 1) * 30.0) for index in range(10)]
    segments = cut_wav(source, specs, tmp_path / "segments")
    assert len(segments) == 10
    assert abs(sum(segment.duration_sec for segment in segments) - 300.0) <= 0.1
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    for segment in segments:
        with wave.open(str(segment.path), "rb") as wav_file:
            assert wav_file.getnframes() / wav_file.getframerate() == pytest.approx(30.0)


def test_silence_detection_returns_suggestions_only(tmp_path: Path) -> None:
    sample_rate = 8000
    time = np.arange(sample_rate // 2) / sample_rate
    tone = (np.sin(2 * math.pi * 220 * time) * 10000).astype(np.int16)
    silence = np.zeros(sample_rate, dtype=np.int16)
    source = tmp_path / "tone_silence_tone.wav"
    write_pcm(source, np.concatenate([tone, silence, tone]), sample_rate)
    intervals = detect_silence(source, min_silence_sec=0.8, threshold_dbfs=-35)
    assert len(intervals) == 1
    assert intervals[0].start_sec == pytest.approx(0.5, abs=0.05)
    assert intervals[0].end_sec == pytest.approx(1.5, abs=0.05)

