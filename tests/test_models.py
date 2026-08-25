from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import CheckConstraint, func, select
from sqlalchemy.exc import IntegrityError

from app.db import Base
from app.models import (
    Asset,
    Episode,
    EpisodeReferencePin,
    Job,
    Reference,
    ReferenceVersion,
    Scene,
    Series,
    Shot,
    SimpleQaNote,
)

ALL_MODELS = (
    Series,
    Episode,
    Scene,
    Shot,
    Reference,
    ReferenceVersion,
    EpisodeReferencePin,
    Asset,
    Job,
    SimpleQaNote,
)

EXPECTED_CHECK_CONSTRAINTS = {
    "ck_reference_type",
    "ck_reference_scope",
    "ck_reference_scope_owner",
    "ck_reference_version_positive",
    "ck_shot_audio_duration",
    "ck_shot_planned_duration",
    "ck_shot_padding",
    "ck_shot_motion_intent",
    "ck_shot_motion_provider",
    "ck_shot_fill_policy",
    "ck_asset_type",
    "ck_asset_version_positive",
    "ck_asset_duration",
    "ck_job_status",
    "ck_job_priority",
    "ck_job_progress",
    "ck_job_attempts",
    "ck_job_credit_type",
}


def build_graph(tmp_path):
    now = datetime.now(timezone.utc)
    series = Series(slug="demo-series", name="Demo Series")
    episode = Episode(
        series=series,
        episode_number=1,
        slug="episode-one",
        title="Episode One",
        effective_resolution="1920x1080",
        effective_fps=30,
        effective_aspect_ratio="16:9",
        root_path=str(tmp_path / "episode"),
    )
    scene = Scene(episode=episode, scene_number=1, order_index=1)
    reference = Reference(
        slug="hero",
        name="Hero",
        reference_type="character",
        scope="series_specific",
        owning_series=series,
    )
    reference_version = ReferenceVersion(
        reference=reference,
        version=1,
        file_path="references/characters/hero_v1.png",
        checksum="abc",
        created_at=now,
    )
    shot = Shot(
        episode=episode,
        scene=scene,
        shot_id="s001",
        order_index=1,
        characters_json=["hero"],
        primary_character_id="hero",
    )
    pin = EpisodeReferencePin(episode=episode, reference=reference, reference_version=reference_version)
    asset = Asset(
        episode=episode,
        shot=shot,
        asset_type="image",
        version=1,
        is_chosen=True,
        file_path="images/chosen/s001_image_v01_chosen.png",
    )
    job = Job(episode=episode, shot=shot, job_type="image_gen")
    note = SimpleQaNote(episode=episode, shot=shot, asset=asset, category="content", note="Check face")
    return series, episode, scene, shot, reference, reference_version, pin, asset, job, note


def test_create_read_delete_every_model(session, tmp_path) -> None:
    records = build_graph(tmp_path)
    session.add_all(records)
    session.commit()

    for model in ALL_MODELS:
        assert session.scalar(select(func.count()).select_from(model)) >= 1

    for record in reversed(records):
        session.delete(record)
    session.commit()
    for model in ALL_MODELS:
        assert session.scalar(select(func.count()).select_from(model)) == 0


def test_orm_metadata_contains_all_migration_check_constraints() -> None:
    actual = {
        constraint.name
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert actual == EXPECTED_CHECK_CONSTRAINTS


def test_primary_character_must_belong_to_characters() -> None:
    with pytest.raises(ValueError, match="must belong"):
        Shot(
            episode_id=1,
            shot_id="s001",
            order_index=1,
            characters_json=["tao_thao"],
            primary_character_id="luu_bi",
        )


def test_empty_characters_require_null_primary() -> None:
    with pytest.raises(ValueError):
        Shot(episode_id=1, shot_id="s001", order_index=1, characters_json=[], primary_character_id="tao_thao")


def test_duplicate_characters_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        Shot(episode_id=1, shot_id="s001", order_index=1, characters_json=["a", "a"])


def test_only_one_chosen_asset_per_shot_type(session, tmp_path) -> None:
    records = build_graph(tmp_path)
    session.add_all(records)
    session.commit()
    episode, shot = records[1], records[3]
    session.add(
        Asset(
            episode=episode,
            shot=shot,
            asset_type="image",
            version=2,
            is_chosen=True,
            file_path="images/chosen/s001_image_v02_chosen.png",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
