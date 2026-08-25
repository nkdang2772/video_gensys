from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.media.ffprobe import probe_video
from app.motion.sprite_parallax import render_sprite_parallax


def test_render_sprite_parallax_clip(
    tmp_path: Path, ffmpeg_executable: str, ffprobe_executable: str
) -> None:
    source = tmp_path / "sprite-source.png"
    image = Image.new("RGB", (640, 360), (35, 55, 80))
    ImageDraw.Draw(image).ellipse((250, 70, 390, 300), fill=(235, 175, 100))
    image.save(source)
    output = render_sprite_parallax(
        source, 1.0, (220, 40, 420, 320), output_path=tmp_path / "sprite.mp4",
        fps=12, ffmpeg_path=ffmpeg_executable,
    )
    metadata = probe_video(output, ffprobe_path=ffprobe_executable)
    assert metadata.duration_sec == pytest.approx(1.0, abs=0.1)
    assert (metadata.width, metadata.height) == (640, 360)
    assert metadata.codec == "h264"


def test_sprite_parallax_rejects_box_outside_image(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (100, 100), "navy").save(source)
    with pytest.raises(ValueError, match="inside"):
        render_sprite_parallax(
            source, 1.0, (20, 20, 120, 90), output_path=tmp_path / "invalid.mp4",
        )
    assert not (tmp_path / "invalid.mp4").exists()
