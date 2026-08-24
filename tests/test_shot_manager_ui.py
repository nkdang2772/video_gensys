from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Shot
from app.services.episode import create_episode
from app.services.series import create_series
from app.services.shot import create_shot
from app.ui.screens.shot_manager import persist_inline_edits


def _ten_shots(session, tmp_path):
    series = create_series(session, name="Generic Series")
    session.commit()
    episode = create_episode(
        session,
        series_id=series.id,
        episode_number=1,
        title="Generic Episode",
        library_root=tmp_path / "library",
    )
    shots = [
        create_shot(
            session,
            episode_id=episode.id,
            shot_id=f"s{index:03d}",
            order_index=index,
            visual_description=f"Before {index}",
        )
        for index in range(1, 11)
    ]
    session.commit()
    return shots


def test_persist_inline_edits_updates_visual_description_for_ten_shots(session, tmp_path) -> None:
    shots = _ten_shots(session, tmp_path)
    originals = {
        shot.id: {
            "id": shot.id,
            "speaker": "",
            "visual_description": shot.visual_description,
            "motion_intent": "static",
            "status": "draft",
        }
        for shot in shots
    }
    edited = [dict(row, visual_description=f"After {index}") for index, row in enumerate(originals.values(), 1)]

    assert persist_inline_edits(session, originals, edited) == 10
    session.commit()

    descriptions = list(session.scalars(select(Shot.visual_description).order_by(Shot.order_index)))
    assert descriptions == [f"After {index}" for index in range(1, 11)]


def test_persist_inline_edits_rejects_row_outside_current_view(session, tmp_path) -> None:
    shots = _ten_shots(session, tmp_path)
    originals = {
        shots[0].id: {
            "id": shots[0].id,
            "speaker": "",
            "visual_description": "Before 1",
            "motion_intent": "static",
            "status": "draft",
        }
    }
    forged = [dict(originals[shots[0].id], id=999_999, visual_description="Forged")]

    with pytest.raises(ValueError, match="not in the current view"):
        persist_inline_edits(session, originals, forged)

    assert session.get(Shot, shots[0].id).visual_description == "Before 1"
