from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import Episode, EpisodeReferencePin, Reference, ReferenceVersion
from app.services import episode as episode_service
from app.services.episode import EPISODE_DIRECTORIES, create_episode
from app.services.errors import EpisodeCreationError, ReferencePinError
from app.services.series import create_series


def prepare_series_with_references(session):
    series = create_series(
        session,
        name="Tam Quốc",
        default_resolution="3840x2160",
        default_fps=25.0,
        default_aspect_ratio="16:9",
        palette_json={"primary": "red"},
        font_config_json={"family": "Noto Sans"},
    )
    session.flush()
    character = Reference(
        slug="tao-thao",
        name="Tào Tháo",
        reference_type="character",
        scope="series_specific",
        owning_series=series,
        current_version=2,
        is_active=True,
    )
    inactive = Reference(
        slug="inactive",
        name="Inactive",
        reference_type="location",
        scope="series_specific",
        owning_series=series,
        current_version=1,
        is_active=False,
    )
    style = Reference(
        slug="shared-style",
        name="Shared Style",
        reference_type="style",
        scope="shared_across_series",
        owning_series=None,
        current_version=3,
        is_active=True,
    )
    session.add_all([character, inactive, style])
    session.flush()
    now = datetime.now(timezone.utc)
    versions = [
        ReferenceVersion(reference=character, version=2, file_path="character.png", checksum="c", created_at=now),
        ReferenceVersion(reference=inactive, version=1, file_path="inactive.png", checksum="i", created_at=now),
        ReferenceVersion(reference=style, version=3, file_path="style.png", checksum="s", created_at=now),
    ]
    session.add_all(versions)
    series.style_anchor_reference = style
    session.commit()
    return series, character, inactive, style


def test_create_episode_snapshots_series_and_builds_folders(session, tmp_path: Path) -> None:
    series, _, _, _ = prepare_series_with_references(session)
    episode = create_episode(
        session,
        series_id=series.id,
        episode_number=1,
        title="Xích Bích",
        library_root=tmp_path,
    )
    assert episode.effective_resolution == "3840x2160"
    assert episode.effective_fps == 25.0
    assert episode.palette_snapshot_json == {"primary": "red"}
    assert episode.font_config_snapshot_json == {"family": "Noto Sans"}
    assert episode.style_anchor_version_snapshot == 3
    assert Path(episode.root_path).name == "ep_01_xich-bich"
    assert all((Path(episode.root_path) / path).is_dir() for path in EPISODE_DIRECTORIES)


def test_create_episode_pins_active_series_references_and_style_anchor(session, tmp_path: Path) -> None:
    series, character, inactive, style = prepare_series_with_references(session)
    episode = create_episode(
        session,
        series_id=series.id,
        episode_number=1,
        title="Xích Bích",
        library_root=tmp_path,
    )
    pins = list(
        session.scalars(
            select(EpisodeReferencePin).where(EpisodeReferencePin.episode_id == episode.id)
        )
    )
    assert {pin.reference_id for pin in pins} == {character.id, style.id}
    assert inactive.id not in {pin.reference_id for pin in pins}
    assert {pin.reference_version.version for pin in pins} == {2, 3}


def test_disk_failure_rolls_back_episode_and_partial_folder(
    session, tmp_path: Path, monkeypatch
) -> None:
    series, _, _, _ = prepare_series_with_references(session)

    def fail_after_partial_write(root: Path) -> None:
        (root / "script").mkdir()
        raise OSError("simulated disk failure")

    monkeypatch.setattr(episode_service, "_create_episode_folder_tree", fail_after_partial_write)
    with pytest.raises(EpisodeCreationError, match="simulated disk failure"):
        create_episode(
            session,
            series_id=series.id,
            episode_number=1,
            title="Xích Bích",
            library_root=tmp_path,
        )

    assert session.scalar(select(func.count()).select_from(Episode)) == 0
    assert session.scalar(select(func.count()).select_from(EpisodeReferencePin)) == 0
    expected_root = tmp_path / "series" / series.slug / "episodes" / "ep_01_xich-bich"
    assert not expected_root.exists()


def test_database_failure_removes_new_folder_but_keeps_existing_episode(
    session, tmp_path: Path
) -> None:
    series, _, _, _ = prepare_series_with_references(session)
    first = create_episode(
        session,
        series_id=series.id,
        episode_number=1,
        title="Xích Bích",
        library_root=tmp_path,
    )
    first_root = Path(first.root_path)

    with pytest.raises(EpisodeCreationError):
        create_episode(
            session,
            series_id=series.id,
            episode_number=1,
            title="Duplicate Number",
            library_root=tmp_path,
        )

    duplicate_root = tmp_path / "series" / series.slug / "episodes" / "ep_01_duplicate-number"
    assert first_root.is_dir()
    assert not duplicate_root.exists()
    assert session.scalar(select(func.count()).select_from(Episode)) == 1


def test_reference_without_current_version_rolls_back_everything(
    session, tmp_path: Path
) -> None:
    series = create_series(session, name="Tam Quốc")
    session.flush()
    reference = Reference(
        slug="missing-version",
        name="Missing Version",
        reference_type="character",
        scope="series_specific",
        owning_series=series,
        current_version=1,
        is_active=True,
    )
    session.add(reference)
    session.commit()

    with pytest.raises(ReferencePinError, match="missing"):
        create_episode(
            session,
            series_id=series.id,
            episode_number=1,
            title="Xích Bích",
            library_root=tmp_path,
        )

    assert session.scalar(select(func.count()).select_from(Episode)) == 0
    expected_root = tmp_path / "series" / series.slug / "episodes" / "ep_01_xich-bich"
    assert not expected_root.exists()
