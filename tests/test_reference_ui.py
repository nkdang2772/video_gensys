from __future__ import annotations

import warnings
from pathlib import Path

from sqlalchemy import func, select

from app.db import Base, create_db_engine, create_session_factory
from app.models import Episode, EpisodeReferencePin, Reference, ReferenceVersion
from app.services.series import create_series


def _by_key(elements, key: str):
    return next(element for element in elements if element.key == key)


def _reference_app(tmp_path: Path, monkeypatch):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from streamlit.testing.v1 import AppTest

    database = tmp_path / "reference_ui.db"
    database_url = f"sqlite:///{database.as_posix()}"
    engine = create_db_engine(database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        series = create_series(session, name="Generic Reference Series")
        session.commit()
        series_id = series.id
    engine.dispose()

    library_root = tmp_path / "library"
    monkeypatch.setenv("VIDEO_GENSYSTEM_DATABASE_URL", database_url)
    monkeypatch.setenv("VIDEO_GENSYSTEM_LIBRARY_ROOT", str(library_root))
    app_file = Path(__file__).parents[1] / "streamlit_app.py"
    at = AppTest.from_file(str(app_file)).run(timeout=20)
    at.session_state["selected_series_id"] = series_id
    _by_key(at.radio, "main_navigation").set_value("References").run(timeout=20)
    return at, database_url, library_root


def test_reference_library_creates_six_character_versions_and_episode_pins(
    tmp_path: Path, monkeypatch
) -> None:
    at, database_url, _library_root = _reference_app(tmp_path, monkeypatch)
    prefix = "reference_character_series_specific"

    for index in range(1, 7):
        _by_key(at.text_input, f"{prefix}_name").input(f"Character {index}")
        _by_key(at.button, f"{prefix}_create").click().run(timeout=20)
        assert not at.exception

    # Every reference receives its first immutable version through the UI.
    for index in range(1, 7):
        source = tmp_path / f"character_{index}.png"
        source.write_bytes(f"generic-reference-{index}".encode())
        _by_key(at.selectbox, f"{prefix}_selected").select(
            f"Character {index} (character-{index})"
        )
        _by_key(at.text_input, f"{prefix}_local_file").input(str(source))
        _by_key(at.button, f"{prefix}_add_version").click().run(timeout=20)
        assert not at.exception

    _by_key(at.radio, "main_navigation").set_value("Episodes").run(timeout=20)
    _by_key(at.text_input, "episode_title").input("Generic Pinned Episode")
    _by_key(at.button, "episode_create_button").click().run(timeout=20)
    assert not at.exception

    verify_engine = create_db_engine(database_url)
    with verify_engine.connect() as connection:
        assert connection.scalar(
            select(func.count()).select_from(Reference).where(
                Reference.reference_type == "character",
                Reference.scope == "series_specific",
            )
        ) == 6
        assert connection.scalar(select(func.count()).select_from(ReferenceVersion)) == 6
        episode_id = connection.scalar(select(Episode.id))
        assert connection.scalar(
            select(func.count()).select_from(EpisodeReferencePin).where(
                EpisodeReferencePin.episode_id == episode_id
            )
        ) == 6
    verify_engine.dispose()


def test_reference_library_requires_a_version_source(tmp_path: Path, monkeypatch) -> None:
    at, database_url, _library_root = _reference_app(tmp_path, monkeypatch)
    prefix = "reference_character_series_specific"
    _by_key(at.text_input, f"{prefix}_name").input("Character Without File")
    _by_key(at.button, f"{prefix}_create").click().run(timeout=20)
    _by_key(at.button, f"{prefix}_add_version").click().run(timeout=20)

    assert not at.exception
    assert any("Choose a local file or upload a version" in message.value for message in at.error)
    verify_engine = create_db_engine(database_url)
    with verify_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Reference)) == 1
        assert connection.scalar(select(func.count()).select_from(ReferenceVersion)) == 0
    verify_engine.dispose()
