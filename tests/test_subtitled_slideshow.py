from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.media.ffprobe import probe_video
from app.media.subtitled_slideshow import SubtitleSlide, render_subtitled_slideshow


def test_render_vietnamese_subtitled_slideshow(
    tmp_path: Path, ffmpeg_executable: str, ffprobe_executable: str
) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (640, 360), (40, 90, 160)).save(first)
    Image.new("RGB", (640, 360), (150, 75, 40)).save(second)
    output = tmp_path / "intro.mp4"

    result = render_subtitled_slideshow(
        [
            SubtitleSlide(first, 0.8, "Trận Xích Bích. Năm 208.", "Này"),
            SubtitleSlide(second, 1.2, "Đêm đốt thuyền trên sông Trường Giang.", "Nọ"),
        ],
        output,
        width=640,
        height=360,
        fps=12,
        ffmpeg_path=ffmpeg_executable,
        ffprobe_path=ffprobe_executable,
    )

    metadata = probe_video(output, ffprobe_path=ffprobe_executable)
    assert result.slide_count == 2
    assert result.duration_sec == pytest.approx(2.0, abs=0.15)
    assert (metadata.width, metadata.height) == (640, 360)
    assert metadata.frame_rate == pytest.approx(12, abs=0.5)


def test_subtitled_slideshow_rejects_missing_image(tmp_path: Path) -> None:
    output = tmp_path / "should-not-exist.mp4"
    with pytest.raises(FileNotFoundError):
        render_subtitled_slideshow(
            [SubtitleSlide(tmp_path / "missing.png", 1.0, "Không được bỏ qua lỗi")],
            output,
        )
    assert not output.exists()
