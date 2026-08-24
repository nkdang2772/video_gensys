from __future__ import annotations

from pathlib import Path

import pytest

from app.models import Episode
from app.services.character_batch import compute_batch_key
from app.services.shot import bulk_update_shots, create_shot, update_shot
from app.services.series import create_series


def create_test_episode(session, root: Path) -> Episode:
    series = create_series(session, name="Generic Documentary")
    episode = Episode(
        series=series,
        episode_number=1,
        slug="episode-one",
        title="Episode One",
        effective_resolution="1920x1080",
        effective_fps=30,
        effective_aspect_ratio="16:9",
        root_path=str(root),
    )
    session.add(episode)
    session.commit()
    return episode


def test_create_shot_computes_character_batch_key(session, tmp_path: Path) -> None:
    episode = create_test_episode(session, tmp_path)
    shot = create_shot(
        session,
        episode_id=episode.id,
        shot_id="S001",
        order_index=1,
        characters_json=["hero", "sidekick"],
        primary_character_id="hero",
    )
    session.commit()
    assert shot.shot_id == "s001"
    assert shot.character_batch_key == compute_batch_key(["hero", "sidekick"])


def test_update_rejects_primary_character_outside_characters(session, tmp_path: Path) -> None:
    episode = create_test_episode(session, tmp_path)
    shot = create_shot(
        session,
        episode_id=episode.id,
        shot_id="s001",
        order_index=1,
        characters_json=["hero"],
        primary_character_id="hero",
    )
    session.commit()
    with pytest.raises(ValueError, match="must belong"):
        update_shot(session, shot.id, primary_character_id="villain")
    assert shot.primary_character_id == "hero"


def test_update_characters_and_primary_together_is_atomic(session, tmp_path: Path) -> None:
    episode = create_test_episode(session, tmp_path)
    shot = create_shot(
        session,
        episode_id=episode.id,
        shot_id="s001",
        order_index=1,
        characters_json=["old"],
        primary_character_id="old",
    )
    session.commit()
    updated = update_shot(
        session,
        shot.id,
        characters_json=["new", "support"],
        primary_character_id="new",
    )
    session.commit()
    assert updated.primary_character_id == "new"
    assert updated.character_batch_key == compute_batch_key(["new", "support"])


def test_bulk_update_20_shots_regenerates_batch_keys(session, tmp_path: Path) -> None:
    episode = create_test_episode(session, tmp_path)
    shots = [
        create_shot(
            session,
            episode_id=episode.id,
            shot_id=f"s{index:03d}",
            order_index=index,
            characters_json=[],
        )
        for index in range(1, 21)
    ]
    session.commit()
    updated = bulk_update_shots(
        session,
        [shot.id for shot in shots],
        characters_json=["hero", "sidekick"],
        primary_character_id="hero",
    )
    session.commit()
    expected = compute_batch_key(["hero", "sidekick"])
    assert len(updated) == 20
    assert all(shot.character_batch_key == expected for shot in updated)
    assert all(shot.primary_character_id == "hero" for shot in updated)


def test_create_shot_rejects_unsafe_identifier(session, tmp_path: Path) -> None:
    episode = create_test_episode(session, tmp_path)
    with pytest.raises(ValueError, match="shot_id may only"):
        create_shot(
            session,
            episode_id=episode.id,
            shot_id="../unsafe",
            order_index=1,
        )
