from __future__ import annotations

import warnings
from pathlib import Path

from sqlalchemy import func, select

from app.db import Base, create_db_engine, create_session_factory
from app.models import Asset, Episode, EpisodeReferencePin, Reference, Series, Shot
from app.services.episode import create_episode
from app.services.reference import add_version, create_reference
from app.services.series import create_series
from app.services.shot import create_shot
from tests.test_ffprobe import write_silent_wav


def element_by_key(elements, key: str):
    return next(element for element in elements if element.key == key)


def test_streamlit_series_episode_import_and_shot_manager(
    tmp_path: Path, monkeypatch, ffprobe_executable: str
) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from streamlit.testing.v1 import AppTest

    database = tmp_path / "ui.db"
    database_url = f"sqlite:///{database.as_posix()}"
    engine = create_db_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    library_root = tmp_path / "library"
    monkeypatch.setenv("VIDEO_GENSYSTEM_DATABASE_URL", database_url)
    monkeypatch.setenv("VIDEO_GENSYSTEM_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("VIDEO_GENSYSTEM_FFPROBE_PATH", ffprobe_executable)

    app_file = Path(__file__).parents[1] / "streamlit_app.py"
    at = AppTest.from_file(str(app_file)).run(timeout=20)
    assert not at.exception
    element_by_key(at.text_input, "series_create_name").input("Tam Quốc")
    element_by_key(at.button, "series_create_button").click().run(timeout=20)
    assert not at.exception
    element_by_key(at.button, "series_open_button").click().run(timeout=20)
    assert not at.exception
    assert any(message.value.startswith("Opened Tam Quốc") for message in at.success)

    element_by_key(at.radio, "main_navigation").set_value("Episodes").run(timeout=20)
    element_by_key(at.text_input, "episode_title").input("Xích Bích")
    element_by_key(at.button, "episode_create_button").click().run(timeout=20)
    assert not at.exception
    element_by_key(at.button, "episode_open_button").click().run(timeout=20)
    assert not at.exception
    assert any(message.value == "Opened 1: Xích Bích" for message in at.success)

    element_by_key(at.radio, "main_navigation").set_value("Shot Manager").run(timeout=20)
    assert not at.exception
    assert any(info.value == "This Episode has no shots. Import a script first." for info in at.info)

    script = tmp_path / "pilot.txt"
    script_lines: list[str] = []
    for index in range(1, 81):
        if (index - 1) % 10 == 0:
            script_lines.append(f"[SCENE: Scene {(index - 1) // 10 + 1}]")
        script_lines.extend(
            [
                f"[SHOT: s{index:03d}]",
                "[SPEAKER: VO]",
                f"[TEXT: Generic narration {index}]",
                f"[VISUAL: Generic visual {index}]",
                f"[MOTION_INTENT: {'pan' if index % 2 else 'static'}]",
            ]
        )
    script.write_text("\n".join(script_lines) + "\n", encoding="utf-8")
    voice_folder = tmp_path / "voice"
    voice_folder.mkdir()
    for index in range(1, 81):
        write_silent_wav(voice_folder / f"s{index:03d}.wav", 0.02)

    element_by_key(at.radio, "main_navigation").set_value("Import").run(timeout=20)
    element_by_key(at.text_input, "import_script_path").input(str(script))
    element_by_key(at.button, "import_script_button").click().run(timeout=20)
    assert not at.exception
    assert any(message.value == "Imported 80 shots" for message in at.success)
    shot_tables = [table.value for table in at.dataframe if "shot_id" in table.value.columns]
    assert any(len(table) == 80 for table in shot_tables)
    element_by_key(at.text_input, "import_voice_folder").input(str(voice_folder))
    element_by_key(at.button, "import_voice_button").click().run(timeout=60)
    assert not at.exception
    assert any(message.value == "Imported 80 audio assets" for message in at.success)

    element_by_key(at.radio, "main_navigation").set_value("Shot Manager").run(timeout=20)
    assert not at.exception
    assert any(header.value == "Shot Manager" for header in at.header)

    # Scene filtering exposes exactly the ten shots imported into Scene 1.
    element_by_key(at.selectbox, "shot_filter_scene").select("Scene 1").run(timeout=20)
    filtered_tables = [table.value for table in at.dataframe if "shot_id" in table.value.columns]
    assert len(filtered_tables) == 1
    assert list(filtered_tables[0]["shot_id"]) == [f"s{index:03d}" for index in range(1, 11)]
    element_by_key(at.selectbox, "shot_filter_scene").select("All").run(timeout=20)

    # Add a generic character reference, then assign it to twenty shots through the UI.
    manager_engine = create_db_engine(database_url)
    manager_factory = create_session_factory(manager_engine)
    with manager_factory() as manager_session:
        series_id = manager_session.scalar(select(Series.id))
        create_reference(
            manager_session,
            name="Hero",
            slug="hero",
            reference_type="character",
            scope="series_specific",
            owning_series_id=series_id,
        )
        manager_session.commit()
    manager_engine.dispose()
    at.run(timeout=20)
    selected_shots = [f"s{index:03d}" for index in range(1, 21)]
    element_by_key(at.multiselect, "shot_bulk_selection").set_value(selected_shots)
    element_by_key(at.multiselect, "shot_bulk_characters").select("Hero (hero)").run(timeout=20)
    element_by_key(at.selectbox, "shot_bulk_primary").select("hero")
    element_by_key(at.button, "shot_bulk_apply").click().run(timeout=20)
    assert any(message.value == "Updated 20 shots" for message in at.success)
    assert len(at.get("audio")) == 1
    element_by_key(at.radio, "main_navigation").set_value("References").run(timeout=20)
    assert not at.exception
    assert any(header.value == "Reference Library" for header in at.header)
    element_by_key(at.radio, "main_navigation").set_value("Image Gallery").run(timeout=20)
    assert not at.exception
    assert any(header.value == "Image Gallery" for header in at.header)
    assert any(caption.value == "No image variations yet." for caption in at.caption)
    element_by_key(at.radio, "main_navigation").set_value("Motion Queue").run(timeout=20)
    assert not at.exception
    assert any(header.value == "Motion Queue" for header in at.header)
    element_by_key(at.radio, "main_navigation").set_value("Preview").run(timeout=20)
    assert not at.exception
    assert any(header.value == "Preview" for header in at.header)
    element_by_key(at.radio, "main_navigation").set_value("QA & Export").run(timeout=20)
    assert not at.exception
    assert any(header.value == "QA & Export" for header in at.header)

    verify_engine = create_db_engine(database_url)
    with verify_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Series)) == 1
        assert connection.scalar(select(func.count()).select_from(Episode)) == 1
        assert connection.scalar(select(func.count()).select_from(Shot)) == 80
        assert connection.scalar(select(func.count()).select_from(Asset)) == 80
        assigned = connection.scalar(
            select(func.count()).select_from(Shot).where(Shot.primary_character_id == "hero")
        )
        assert assigned == 20
    verify_engine.dispose()


def test_streamlit_series_create_reports_empty_name(tmp_path: Path, monkeypatch) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from streamlit.testing.v1 import AppTest

    database = tmp_path / "ui_error.db"
    database_url = f"sqlite:///{database.as_posix()}"
    engine = create_db_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setenv("VIDEO_GENSYSTEM_DATABASE_URL", database_url)
    monkeypatch.setenv("VIDEO_GENSYSTEM_LIBRARY_ROOT", str(tmp_path / "library"))

    app_file = Path(__file__).parents[1] / "streamlit_app.py"
    at = AppTest.from_file(str(app_file)).run(timeout=20)
    element_by_key(at.button, "series_create_button").click().run(timeout=20)

    assert not at.exception
    assert any("Series name cannot be empty" in message.value for message in at.error)
    verify_engine = create_db_engine(database_url)
    with verify_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Series)) == 0
    verify_engine.dispose()


def test_streamlit_import_requires_a_script_source(tmp_path: Path, monkeypatch) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from streamlit.testing.v1 import AppTest

    database = tmp_path / "ui_import_error.db"
    database_url = f"sqlite:///{database.as_posix()}"
    engine = create_db_engine(database_url)
    Base.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setenv("VIDEO_GENSYSTEM_DATABASE_URL", database_url)
    monkeypatch.setenv("VIDEO_GENSYSTEM_LIBRARY_ROOT", str(tmp_path / "library"))

    app_file = Path(__file__).parents[1] / "streamlit_app.py"
    at = AppTest.from_file(str(app_file)).run(timeout=20)
    element_by_key(at.text_input, "series_create_name").input("Import Error Series")
    element_by_key(at.button, "series_create_button").click().run(timeout=20)
    element_by_key(at.radio, "main_navigation").set_value("Episodes").run(timeout=20)
    element_by_key(at.text_input, "episode_title").input("Empty Import")
    element_by_key(at.button, "episode_create_button").click().run(timeout=20)
    element_by_key(at.radio, "main_navigation").set_value("Import").run(timeout=20)
    element_by_key(at.button, "import_script_button").click().run(timeout=20)

    assert not at.exception
    assert any("Choose a script file" in message.value for message in at.error)
    verify_engine = create_db_engine(database_url)
    with verify_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Shot)) == 0
    verify_engine.dispose()


def test_shot_manager_bulk_assignment_requires_a_shot(tmp_path: Path, monkeypatch) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from streamlit.testing.v1 import AppTest

    database = tmp_path / "ui_shot_error.db"
    database_url = f"sqlite:///{database.as_posix()}"
    engine = create_db_engine(database_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        series = create_series(session, name="Shot Error Series")
        session.commit()
        episode = create_episode(
            session,
            series_id=series.id,
            episode_number=1,
            title="Shot Error Episode",
            library_root=tmp_path / "library",
        )
        create_shot(
            session,
            episode_id=episode.id,
            shot_id="s001",
            order_index=1,
        )
        session.commit()
        episode_id = episode.id
    engine.dispose()
    monkeypatch.setenv("VIDEO_GENSYSTEM_DATABASE_URL", database_url)
    monkeypatch.setenv("VIDEO_GENSYSTEM_LIBRARY_ROOT", str(tmp_path / "library"))

    app_file = Path(__file__).parents[1] / "streamlit_app.py"
    at = AppTest.from_file(str(app_file)).run(timeout=20)
    at.session_state["selected_episode_id"] = episode_id
    element_by_key(at.radio, "main_navigation").set_value("Shot Manager").run(timeout=20)
    element_by_key(at.button, "shot_bulk_apply").click().run(timeout=20)

    assert not at.exception
    assert any("Select at least one shot" in message.value for message in at.error)


def test_six_generic_character_references_are_pinned_when_episode_is_created(
    session, tmp_path: Path
) -> None:
    series = create_series(session, name="Any Series")
    session.commit()
    for index in range(1, 7):
        reference = create_reference(
            session,
            name=f"Character {index}",
            slug=f"character_{index}",
            reference_type="character",
            scope="series_specific",
            owning_series_id=series.id,
        )
        session.commit()
        source = tmp_path / f"character_{index}.png"
        source.write_bytes(f"reference-{index}".encode())
        add_version(
            session,
            reference_id=reference.id,
            source_path=source,
            library_root=tmp_path / "library",
        )

    episode = create_episode(
        session,
        series_id=series.id,
        episode_number=1,
        title="Example Episode",
        library_root=tmp_path / "library",
    )
    pins = session.scalar(
        select(func.count())
        .select_from(EpisodeReferencePin)
        .where(EpisodeReferencePin.episode_id == episode.id)
    )
    assert pins == 6
