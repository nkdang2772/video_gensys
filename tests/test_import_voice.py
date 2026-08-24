from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import Asset, Episode, Shot
from app.services import import_voice as import_voice_service
from app.services.import_voice import VoiceImportError, import_voice_folder, match_shot_id
from app.services.series import create_series
from tests.test_ffprobe import write_silent_wav


def create_episode_with_shots(session, root: Path, count: int = 80) -> Episode:
    series = create_series(session, name="Tam Quốc")
    episode_root = root / "episode"
    (episode_root / "audio" / "source").mkdir(parents=True)
    episode = Episode(
        series=series,
        episode_number=1,
        slug="xich-bich",
        title="Xích Bích",
        effective_resolution="1920x1080",
        effective_fps=30,
        effective_aspect_ratio="16:9",
        root_path=str(episode_root),
    )
    session.add(episode)
    session.flush()
    session.add_all(
        Shot(
            episode=episode,
            shot_id=f"s{index:03d}",
            order_index=index,
            characters_json=[],
        )
        for index in range(1, count + 1)
    )
    session.commit()
    return episode


def test_match_shot_id_supports_s_pattern_and_keyword_prefix() -> None:
    known = {"s001", "cold_open"}
    assert match_shot_id("voice_s001_take.wav", known) == "s001"
    assert match_shot_id("cold_open-narration.wav", known) == "cold_open"
    assert match_shot_id("unknown.wav", known) is None


def test_import_80_real_wavs_and_report_unmatched_file(
    session, tmp_path: Path, ffprobe_executable: str
) -> None:
    episode = create_episode_with_shots(session, tmp_path)
    voice_folder = tmp_path / "voice"
    voice_folder.mkdir()
    for index in range(1, 81):
        write_silent_wav(voice_folder / f"narration_s{index:03d}_take.wav", 0.02)
    write_silent_wav(voice_folder / "wrong_name.wav", 0.02)

    report = import_voice_folder(
        session,
        episode_id=episode.id,
        folder=voice_folder,
        ffprobe_path=ffprobe_executable,
    )

    assert len(report.imported_assets) == 80
    assert session.scalar(select(func.count()).select_from(Asset)) == 80
    assert all(asset.asset_type == "audio" and asset.is_chosen for asset in report.imported_assets)
    assert all(asset.duration_sec > 0 for asset in report.imported_assets)
    imported_shots = list(
        session.scalars(select(Shot).where(Shot.episode_id == episode.id).order_by(Shot.order_index))
    )
    assert all(shot.audio_start_sec == 0 for shot in imported_shots)
    assert all(shot.audio_end_sec == shot.audio_duration_sec > 0 for shot in imported_shots)
    assert [warning.code for warning in report.warnings] == ["unmatched_file"]
    assert Path(report.warnings[0].file_path).name == "wrong_name.wav"


def test_broken_matched_wav_is_reported_and_not_silently_imported(
    session, tmp_path: Path, ffprobe_executable: str
) -> None:
    episode = create_episode_with_shots(session, tmp_path, count=1)
    voice_folder = tmp_path / "voice"
    voice_folder.mkdir()
    (voice_folder / "s001.wav").write_bytes(b"broken")
    report = import_voice_folder(
        session,
        episode_id=episode.id,
        folder=voice_folder,
        ffprobe_path=ffprobe_executable,
    )
    assert not report.imported_assets
    assert {warning.code for warning in report.warnings} == {
        "probe_failed",
        "missing_audio_for_shot",
    }


def test_filename_with_two_known_shot_ids_is_reported_and_not_guessed(
    session, tmp_path: Path, ffprobe_executable: str
) -> None:
    episode = create_episode_with_shots(session, tmp_path, count=2)
    voice_folder = tmp_path / "voice"
    voice_folder.mkdir()
    write_silent_wav(voice_folder / "s001_s002.wav", 0.02)

    report = import_voice_folder(
        session,
        episode_id=episode.id,
        folder=voice_folder,
        ffprobe_path=ffprobe_executable,
    )

    assert not report.imported_assets
    assert [warning.code for warning in report.warnings] == [
        "unmatched_file",
        "missing_audio_for_shot",
        "missing_audio_for_shot",
    ]
    assert {warning.shot_id for warning in report.warnings[1:]} == {"s001", "s002"}


def test_valid_second_candidate_imports_after_first_candidate_is_broken(
    session, tmp_path: Path, ffprobe_executable: str
) -> None:
    episode = create_episode_with_shots(session, tmp_path, count=1)
    voice_folder = tmp_path / "voice"
    voice_folder.mkdir()
    (voice_folder / "a_s001.wav").write_bytes(b"broken")
    write_silent_wav(voice_folder / "b_s001.wav", 0.02)
    report = import_voice_folder(
        session,
        episode_id=episode.id,
        folder=voice_folder,
        ffprobe_path=ffprobe_executable,
    )
    assert len(report.imported_assets) == 1
    assert [warning.code for warning in report.warnings] == ["probe_failed"]


def test_failure_after_copy_rolls_back_database_and_removes_file(
    session, tmp_path: Path, ffprobe_executable: str, monkeypatch
) -> None:
    episode = create_episode_with_shots(session, tmp_path, count=1)
    voice_folder = tmp_path / "voice"
    voice_folder.mkdir()
    write_silent_wav(voice_folder / "s001.wav", 0.02)

    def fail_checksum(_path: Path) -> str:
        raise OSError("simulated checksum failure")

    monkeypatch.setattr(import_voice_service, "_checksum", fail_checksum)
    with pytest.raises(OSError, match="checksum failure"):
        import_voice_folder(
            session,
            episode_id=episode.id,
            folder=voice_folder,
            ffprobe_path=ffprobe_executable,
        )
    assert session.scalar(select(func.count()).select_from(Asset)) == 0
    assert not list((Path(episode.root_path) / "audio" / "source").glob("*.wav"))


def test_import_rejects_unsafe_shot_id_before_copy(
    session, tmp_path: Path, ffprobe_executable: str
) -> None:
    episode = create_episode_with_shots(session, tmp_path, count=1)
    shot = session.scalar(select(Shot).where(Shot.episode_id == episode.id))
    shot.shot_id = "../unsafe"
    session.commit()
    voice_folder = tmp_path / "voice"
    voice_folder.mkdir()
    write_silent_wav(voice_folder / "s001.wav", 0.02)
    with pytest.raises(VoiceImportError, match="Unsafe shot_id"):
        import_voice_folder(
            session,
            episode_id=episode.id,
            folder=voice_folder,
            ffprobe_path=ffprobe_executable,
        )


def test_reimport_creates_new_version_and_switches_chosen_asset(
    session, tmp_path: Path, ffprobe_executable: str
) -> None:
    episode = create_episode_with_shots(session, tmp_path, count=1)
    first_folder = tmp_path / "voice_v1"
    first_folder.mkdir()
    write_silent_wav(first_folder / "s001.wav", 0.02)
    first_report = import_voice_folder(
        session,
        episode_id=episode.id,
        folder=first_folder,
        ffprobe_path=ffprobe_executable,
    )

    second_folder = tmp_path / "voice_v2"
    second_folder.mkdir()
    write_silent_wav(second_folder / "s001.wav", 0.04)
    second_report = import_voice_folder(
        session,
        episode_id=episode.id,
        folder=second_folder,
        ffprobe_path=ffprobe_executable,
    )

    assets = list(session.scalars(select(Asset).order_by(Asset.version)))
    assert [asset.version for asset in assets] == [1, 2]
    assert [asset.is_chosen for asset in assets] == [False, True]
    assert first_report.imported_assets[0].id != second_report.imported_assets[0].id
    assert not second_report.warnings
