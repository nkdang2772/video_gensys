from __future__ import annotations

import warnings
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, create_db_engine
from app.models import Asset, Episode, Job, Series, Shot
from app.services.motion_generation import enqueue_motion_job


def _by_key(elements, key: str):
    return next(element for element in elements if element.key == key)


def _setup_motion_queue(tmp_path: Path, monkeypatch, *, with_source_image: bool):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from streamlit.testing.v1 import AppTest

    database = tmp_path / "motion_queue_ui.db"
    database_url = f"sqlite:///{database.as_posix()}"
    engine = create_db_engine(database_url)
    Base.metadata.create_all(engine)
    root = tmp_path / "library" / "episode"
    (root / "images" / "generated").mkdir(parents=True)
    (root / "clips" / "generated").mkdir(parents=True)
    with Session(engine) as session, session.begin():
        episode = Episode(
            series=Series(slug="motion-series", name="Motion Series"),
            episode_number=1,
            slug="motion-episode",
            title="Motion Episode",
            effective_resolution="1280x720",
            effective_fps=12,
            effective_aspect_ratio="16:9",
            root_path=str(root),
        )
        shot = Shot(
            episode=episode,
            shot_id="s001",
            order_index=1,
            visual_description="A generic camera move",
            audio_duration_sec=1.0,
            motion_fill_policy="extend",
        )
        session.add_all([episode, shot])
        session.flush()
        if with_source_image:
            image_path = root / "images" / "generated" / "s001.png"
            image_path.write_bytes(b"source-image")
            session.add(
                Asset(
                    episode_id=episode.id,
                    shot_id=shot.id,
                    asset_type="image",
                    version=1,
                    is_chosen=True,
                    provider="manual",
                    file_path="images/generated/s001.png",
                )
            )
            session.flush()
        episode_id = episode.id
        shot_id = shot.id
    engine.dispose()

    monkeypatch.setenv("VIDEO_GENSYSTEM_DATABASE_URL", database_url)
    monkeypatch.setenv("VIDEO_GENSYSTEM_LIBRARY_ROOT", str(tmp_path / "library"))
    app_file = Path(__file__).parents[1] / "streamlit_app.py"
    at = AppTest.from_file(str(app_file)).run(timeout=20)
    at.session_state["selected_episode_id"] = episode_id
    _by_key(at.radio, "main_navigation").set_value("Motion Queue").run(timeout=20)
    return at, database_url, root, shot_id


def test_motion_queue_ui_retries_failed_job_and_chooses_variation(
    tmp_path: Path, monkeypatch
) -> None:
    at, database_url, root, shot_id = _setup_motion_queue(
        tmp_path, monkeypatch, with_source_image=True
    )
    first_path = root / "clips" / "generated" / "s001_v01.mp4"
    second_path = root / "clips" / "generated" / "s001_v02.mp4"
    first_path.write_bytes(b"\x00\x00\x00\x18ftypisom-first")
    second_path.write_bytes(b"\x00\x00\x00\x18ftypisom-second")
    engine = create_db_engine(database_url)
    with Session(engine) as session, session.begin():
        job = enqueue_motion_job(session, shot_id=shot_id, provider="wan_local")
        job.status = "failed"
        job.progress_percent = 40
        job.attempt_count = 3
        job.error_message = "provider timeout"
        first = Asset(
            episode_id=job.episode_id,
            shot_id=shot_id,
            asset_type="video",
            version=1,
            is_chosen=True,
            provider="wan_local",
            file_path="clips/generated/s001_v01.mp4",
            duration_sec=1.0,
        )
        second = Asset(
            episode_id=job.episode_id,
            shot_id=shot_id,
            asset_type="video",
            version=2,
            is_chosen=False,
            provider="wan_local",
            file_path="clips/generated/s001_v02.mp4",
            duration_sec=1.0,
        )
        session.add_all([first, second])
        session.flush()
        job_id = job.id
        second_id = second.id
    engine.dispose()

    at.run(timeout=20)
    assert not at.exception
    assert {caption.value for caption in at.caption} >= {
        "v1 · wan_local · 1.00s",
        "v2 · wan_local · 1.00s",
    }
    choose_buttons = [
        button for button in at.button if (button.key or "").startswith("motion_choose_")
    ]
    assert len(choose_buttons) == 2
    assert sum(button.disabled for button in choose_buttons) == 1
    _by_key(at.button, f"motion_retry_{job_id}").click().run(timeout=20)
    _by_key(at.button, f"motion_choose_{second_id}").click().run(timeout=20)

    assert not at.exception
    verify_engine = create_db_engine(database_url)
    with Session(verify_engine) as session:
        retried = session.get(Job, job_id)
        chosen = session.scalar(
            select(Asset).where(
                Asset.shot_id == shot_id,
                Asset.asset_type == "video",
                Asset.is_chosen.is_(True),
            )
        )
        assert retried is not None
        assert retried.status == "queued" and retried.attempt_count == 0
        assert retried.error_message is None
        assert chosen is not None and chosen.id == second_id
    verify_engine.dispose()


def test_motion_queue_ui_reports_missing_source_image(tmp_path: Path, monkeypatch) -> None:
    at, database_url, _root, _shot_id = _setup_motion_queue(
        tmp_path, monkeypatch, with_source_image=False
    )

    _by_key(at.button, "motion_enqueue").click().run(timeout=20)

    assert not at.exception
    assert any("requires a chosen source image" in message.value for message in at.error)
    verify_engine = create_db_engine(database_url)
    with Session(verify_engine) as session:
        assert session.scalar(select(Job.id)) is None
    verify_engine.dispose()
