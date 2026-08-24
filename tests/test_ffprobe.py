from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import pytest

import app.media.ffprobe as ffprobe_module
from app.media.ffprobe import FFprobeError, probe_audio


def write_silent_wav(path: Path, duration_sec: float, *, sample_rate: int = 16000) -> None:
    frame_count = round(duration_sec * sample_rate)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(b"\x00\x00" * frame_count)


def test_probe_short_real_wav(tmp_path: Path, ffprobe_executable: str) -> None:
    path = tmp_path / "short.wav"
    write_silent_wav(path, 0.125)
    metadata = probe_audio(path, ffprobe_path=ffprobe_executable)
    assert metadata.duration_sec == pytest.approx(0.125, abs=0.001)
    assert metadata.sample_rate == 16000
    assert metadata.channels == 1
    assert metadata.codec == "pcm_s16le"


def test_probe_long_real_wav(tmp_path: Path, ffprobe_executable: str) -> None:
    path = tmp_path / "long.wav"
    write_silent_wav(path, 1.25, sample_rate=22050)
    metadata = probe_audio(path, ffprobe_path=ffprobe_executable)
    assert metadata.duration_sec == pytest.approx(1.25, abs=0.001)
    assert metadata.sample_rate == 22050


def test_probe_rejects_broken_wav(tmp_path: Path, ffprobe_executable: str) -> None:
    path = tmp_path / "broken.wav"
    path.write_bytes(b"not a wave file")
    with pytest.raises(FFprobeError, match="ffprobe failed"):
        probe_audio(path, ffprobe_path=ffprobe_executable)


def test_probe_rejects_zero_duration_wav(tmp_path: Path, ffprobe_executable: str) -> None:
    path = tmp_path / "zero.wav"
    write_silent_wav(path, 0)
    with pytest.raises(FFprobeError, match="duration"):
        probe_audio(path, ffprobe_path=ffprobe_executable)


def test_probe_uses_default_30_second_timeout(
    tmp_path: Path, ffprobe_executable: str, monkeypatch
) -> None:
    path = tmp_path / "timeout.wav"
    write_silent_wav(path, 0.125)
    observed: dict[str, float] = {}

    def simulate_timeout(command, **kwargs):
        observed["timeout"] = kwargs["timeout"]
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(ffprobe_module.subprocess, "run", simulate_timeout)
    with pytest.raises(FFprobeError, match="timed out after 30 seconds"):
        probe_audio(path, ffprobe_path=ffprobe_executable)
    assert observed == {"timeout": 30.0}
