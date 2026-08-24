from __future__ import annotations

import warnings
from pathlib import Path

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Base, create_db_engine
from app.models import Asset, Episode, Job, Series, Shot
from app.services.character_batch import compute_batch_key


def _by_key(elements, key: str):
    return next(element for element in elements if element.key == key)


def _setup_gallery(tmp_path: Path, monkeypatch, *, shot_count: int):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from streamlit.testing.v1 import AppTest

    database = tmp_path / "gallery_ui.db"
    database_url = f"sqlite:///{database.as_posix()}"
    engine = create_db_engine(database_url)
    Base.metadata.create_all(engine)
    root = tmp_path / "library" / "episode"
    (root / "images" / "generated").mkdir(parents=True)
    with Session(engine) as session, session.begin():
        series = Series(slug="gallery-series", name="Gallery Series")
        episode = Episode(
            series=series,
            episode_number=1,
            slug="gallery-episode",
            title="Gallery Episode",
            effective_resolution="1920x1080",
            effective_fps=30,
            effective_aspect_ratio="16:9",
            root_path=str(root),
        )
        shots = [
            Shot(
                episode=episode,
                shot_id=f"s{index:03d}",
                order_index=index,
                visual_description=f"Generic visual {index}",
                characters_json=["hero"] if index % 2 else ["support"],
                character_batch_key=compute_batch_key(
                    ["hero"] if index % 2 else ["support"]
                ),
            )
            for index in range(1, shot_count + 1)
        ]
        session.add_all([episode, *shots])
        session.flush()
        episode_id = episode.id
        shot_ids = [shot.id for shot in shots]
    engine.dispose()

    monkeypatch.setenv("VIDEO_GENSYSTEM_DATABASE_URL", database_url)
    monkeypatch.setenv("VIDEO_GENSYSTEM_LIBRARY_ROOT", str(tmp_path / "library"))
    app_file = Path(__file__).parents[1] / "streamlit_app.py"
    at = AppTest.from_file(str(app_file)).run(timeout=20)
    at.session_state["selected_episode_id"] = episode_id
    _by_key(at.radio, "main_navigation").set_value("Image Gallery").run(timeout=20)
    return at, database_url, root, shot_ids


def test_image_gallery_chooses_variation_and_queues_edited_prompt(
    tmp_path: Path, monkeypatch
) -> None:
    at, database_url, root, shot_ids = _setup_gallery(tmp_path, monkeypatch, shot_count=1)
    first_path = root / "images" / "generated" / "s001_v01.png"
    second_path = root / "images" / "generated" / "s001_v02.png"
    Image.new("RGB", (4, 4), (20, 40, 60)).save(first_path)
    Image.new("RGB", (4, 4), (80, 100, 120)).save(second_path)
    engine = create_db_engine(database_url)
    with Session(engine) as session, session.begin():
        first = Asset(
            episode_id=1,
            shot_id=shot_ids[0],
            asset_type="image",
            version=1,
            is_chosen=True,
            provider="manual",
            file_path=first_path.relative_to(root).as_posix(),
        )
        second = Asset(
            episode_id=1,
            shot_id=shot_ids[0],
            asset_type="image",
            version=2,
            is_chosen=False,
            provider="manual",
            file_path=second_path.relative_to(root).as_posix(),
        )
        session.add_all([first, second])
        session.flush()
        second_id = second.id
    engine.dispose()

    at.run(timeout=20)
    assert len(at.get("imgs")) == 2
    _by_key(at.button, f"gallery_choose_{second_id}").click().run(timeout=20)
    source = tmp_path / "regenerate.png"
    Image.new("RGB", (4, 4), (140, 160, 180)).save(source)
    _by_key(at.text_area, "gallery_prompt").input("Edited generic prompt")
    _by_key(at.text_input, "gallery_single_manual_path").input(str(source))
    _by_key(at.button, "gallery_enqueue").click().run(timeout=20)

    assert not at.exception
    assert any(message.value.startswith("Queued image Job #") for message in at.success)
    verify_engine = create_db_engine(database_url)
    with Session(verify_engine) as session:
        chosen = session.scalar(
            select(Asset).where(Asset.shot_id == shot_ids[0], Asset.is_chosen.is_(True))
        )
        assert chosen is not None and chosen.id == second_id
        job = session.scalar(select(Job))
        assert job is not None
        assert job.input_payload_json["prompt"] == "Edited generic prompt"
        assert job.input_payload_json["provider"] == "manual"
    verify_engine.dispose()


def test_image_gallery_batch_button_queues_eighty_sorted_jobs_and_rejects_manual(
    tmp_path: Path, monkeypatch
) -> None:
    at, database_url, _root, _shot_ids = _setup_gallery(tmp_path, monkeypatch, shot_count=80)

    _by_key(at.selectbox, "gallery_batch_provider").select("manual").run(timeout=20)
    _by_key(at.button, "gallery_batch_enqueue").click().run(timeout=20)
    assert any("Manual provider is only available" in message.value for message in at.error)

    _by_key(at.selectbox, "gallery_batch_provider").select("google_flow").run(timeout=20)
    _by_key(at.button, "gallery_batch_enqueue").click().run(timeout=20)
    assert not at.exception
    assert any(message.value == "Queued 80 image jobs" for message in at.success)

    verify_engine = create_db_engine(database_url)
    with Session(verify_engine) as session:
        jobs = list(session.scalars(select(Job).order_by(Job.id)))
        assert len(jobs) == 80
        assert all(job.priority == "overnight" and job.status == "queued" for job in jobs)
        keys = [job.input_payload_json["character_batch_key"] for job in jobs]
        assert keys == sorted(keys)
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
    verify_engine.dispose()
