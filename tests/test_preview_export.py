from __future__ import annotations

import csv
import hashlib
import json
import wave
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy.orm import Session

from app.export.package import MANIFEST_COLUMNS, export_episode_package
from app.media.concat import render_sequence_preview, render_shot_preview
from app.media.ffprobe import probe_video
from app.models import Asset, Episode, Scene, Series, Shot
from app.qa.checker import run_asset_checks


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wav(path: Path, duration: float = 1.0, rate: int = 16000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\0\0" * round(duration * rate))
    return path


def _episode(session: Session, tmp_path: Path, count: int = 3) -> tuple[Episode, Scene, list[Shot]]:
    root = tmp_path / "generic-preview-episode"
    for folder in ("audio/source", "images/chosen", "clips/chosen", "proxies", "qa", "export"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    series = Series(slug="generic-series", name="Generic Series")
    episode = Episode(
        series=series, episode_number=1, slug="generic-episode", title="Generic Episode",
        effective_resolution="1280x720", effective_fps=24, effective_aspect_ratio="16:9",
        root_path=str(root),
    )
    scene = Scene(episode=episode, scene_number=1, title="Opening", order_index=1)
    shots: list[Shot] = []
    for index in range(1, count + 1):
        shot = Shot(
            episode=episode, scene=scene, shot_id=f"s{index:03d}", order_index=index,
            speaker="Narrator", audio_duration_sec=1.0, motion_fill_policy="extend",
            notes=f"Editorial note {index}",
        )
        audio = _wav(root / "audio" / "source" / f"s{index:03d}.wav")
        shot.assets.append(Asset(
            episode=episode, asset_type="audio", version=1, is_chosen=True,
            file_path=audio.relative_to(root).as_posix(), duration_sec=1.0,
            codec="pcm_s16le", file_size=audio.stat().st_size, checksum=_checksum(audio),
        ))
        shots.append(shot)
    session.add(episode)
    session.flush()
    return episode, scene, shots


def _add_image(episode: Episode, shot: Shot, color: tuple[int, int, int]) -> Asset:
    root = Path(episode.root_path)
    image = root / "images" / "chosen" / f"{shot.shot_id}.png"
    Image.new("RGB", (1280, 720), color).save(image)
    asset = Asset(
        episode=episode, shot=shot, asset_type="image", version=1, is_chosen=True,
        file_path=image.relative_to(root).as_posix(), width=1280, height=720,
        file_size=image.stat().st_size, checksum=_checksum(image),
    )
    shot.assets.append(asset)
    return asset


def test_preview_three_shots_scene_and_full_with_red_placeholder(
    session: Session, tmp_path: Path, ffmpeg_executable: str, ffprobe_executable: str
) -> None:
    episode, scene, shots = _episode(session, tmp_path)
    _add_image(episode, shots[0], (40, 100, 180))
    _add_image(episode, shots[1], (40, 170, 80))
    session.flush()

    third = render_shot_preview(
        episode, shots[2], ffmpeg_path=ffmpeg_executable,
        ffprobe_path=ffprobe_executable, force=True,
    )
    assert third.placeholder_shot_ids == ("s003",)
    scene_result = render_sequence_preview(
        session, episode.id, scene_id=scene.id, ffmpeg_path=ffmpeg_executable,
        ffprobe_path=ffprobe_executable, force=True,
    )
    full_result = render_sequence_preview(
        session, episode.id, ffmpeg_path=ffmpeg_executable,
        ffprobe_path=ffprobe_executable, force=True,
    )
    assert scene_result.shot_count == full_result.shot_count == 3
    assert scene_result.placeholder_shot_ids == full_result.placeholder_shot_ids == ("s003",)
    cached = render_sequence_preview(
        session, episode.id, ffmpeg_path=ffmpeg_executable,
        ffprobe_path=ffprobe_executable, force=False,
    )
    assert cached.placeholder_shot_ids == ("s003",)
    metadata = probe_video(full_result.output_path, ffprobe_path=ffprobe_executable)
    assert (metadata.width, metadata.height) == (1280, 720)
    assert metadata.frame_rate == pytest.approx(24)
    assert metadata.duration_sec == pytest.approx(3.0, abs=0.15)


def test_checker_lists_placeholder_and_writes_html_json(
    session: Session, tmp_path: Path, ffmpeg_executable: str, ffprobe_executable: str
) -> None:
    episode, _scene, shots = _episode(session, tmp_path, 1)
    session.flush()
    report = run_asset_checks(session, episode.id, ffmpeg_path=ffmpeg_executable, ffprobe_path=ffprobe_executable)
    assert not report.passed
    assert report.placeholder_shot_ids == (shots[0].shot_id,)
    assert {issue.code for issue in report.issues} >= {"missing_visual", "placeholder"}
    payload = json.loads(report.json_path.read_text(encoding="utf-8"))
    assert payload["placeholder_shot_ids"] == ["s001"]
    assert "Manual review still required" in report.html_path.read_text(encoding="utf-8")


def test_export_package_has_exactly_sixteen_columns(
    session: Session, tmp_path: Path, ffmpeg_executable: str, ffprobe_executable: str
) -> None:
    episode, scene, shots = _episode(session, tmp_path, 3)
    _add_image(episode, shots[0], (30, 90, 170))
    _add_image(episode, shots[1], (180, 100, 30))
    _add_image(episode, shots[2], (120, 50, 170))
    session.flush()
    scene_preview = render_sequence_preview(
        session, episode.id, scene_id=scene.id, ffmpeg_path=ffmpeg_executable,
        ffprobe_path=ffprobe_executable, force=True,
    )
    assert scene_preview.shot_count == 3 and scene_preview.output_path.is_file()
    preview = render_sequence_preview(
        session, episode.id, ffmpeg_path=ffmpeg_executable,
        ffprobe_path=ffprobe_executable, force=True,
    )
    assert preview.shot_count == 3 and preview.output_path.is_file()
    result = export_episode_package(session, episode.id, ffmpeg_path=ffmpeg_executable, ffprobe_path=ffprobe_executable)
    assert result.qa_report.passed
    with result.manifest_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert tuple(reader.fieldnames) == MANIFEST_COLUMNS
    assert len(reader.fieldnames) == 16
    assert len(rows) == result.shot_count == 3
    assert result.media_file_count == 6
    assert all((result.export_path / row["audio_path"]).is_file() for row in rows)
    assert all((result.export_path / row["image_path"]).is_file() for row in rows)
    project = json.loads(result.project_manifest_path.read_text(encoding="utf-8"))
    assert project["episode"]["fps"] == 24.0
    assert project["editor_profile"] == {"name": "davinci_resolve", "timeline_fps": 24.0}
    assert project["shot_notes"] == {
        "s001": "Editorial note 1", "s002": "Editorial note 2", "s003": "Editorial note 3"
    }
    assert "16 cột" in result.readme_path.read_text(encoding="utf-8")
    rebuilt = export_episode_package(
        session, episode.id, ffmpeg_path=ffmpeg_executable,
        ffprobe_path=ffprobe_executable, force=True,
    )
    assert rebuilt.manifest_path.is_file()
    assert len(list(Path(episode.root_path).glob("export_backup_*"))) == 1


def test_export_rejects_fps_unsupported_by_davinci_profile(
    session: Session, tmp_path: Path, ffmpeg_executable: str, ffprobe_executable: str
) -> None:
    episode, _scene, _shots = _episode(session, tmp_path, 1)
    episode.effective_fps = 12
    session.flush()

    with pytest.raises(ValueError, match=r"Episode FPS 12 .* not supported.*DaVinci Resolve"):
        export_episode_package(
            session,
            episode.id,
            ffmpeg_path=ffmpeg_executable,
            ffprobe_path=ffprobe_executable,
        )

    assert not any((Path(episode.root_path) / "export").iterdir())
