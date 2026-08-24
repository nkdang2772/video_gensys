from __future__ import annotations

import warnings
from pathlib import Path

from sqlalchemy import func, select

from app.db import Base, create_db_engine
from app.models import Asset, Episode, EpisodeReferencePin, Series, Shot
from app.services.episode import create_episode
from app.services.reference import add_version, create_reference
from app.services.series import create_series
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
    element_by_key(at.text_input, "series_create_name").input("Generic Series")
    element_by_key(at.button, "series_create_button").click().run(timeout=20)
    assert not at.exception

    element_by_key(at.radio, "main_navigation").set_value("Episodes").run(timeout=20)
    element_by_key(at.text_input, "episode_title").input("Pilot Episode")
    element_by_key(at.button, "episode_create_button").click().run(timeout=20)
    assert not at.exception

    element_by_key(at.radio, "main_navigation").set_value("Shot Manager").run(timeout=20)
    assert not at.exception
    assert any(info.value == "This Episode has no shots. Import a script first." for info in at.info)

    script = tmp_path / "pilot.txt"
    script.write_text(
        """[SCENE: Opening]
[SHOT: s001]
[SPEAKER: VO]
[TEXT: Generic narration one]
[VISUAL: Generic visual one]
[MOTION_INTENT: pan]
[SHOT: s002]
[SPEAKER: VO]
[TEXT: Generic narration two]
[VISUAL: Generic visual two]
[MOTION_INTENT: static]
""",
        encoding="utf-8",
    )
    voice_folder = tmp_path / "voice"
    voice_folder.mkdir()
    write_silent_wav(voice_folder / "s001.wav", 0.02)
    write_silent_wav(voice_folder / "s002.wav", 0.03)

    element_by_key(at.radio, "main_navigation").set_value("Import").run(timeout=20)
    element_by_key(at.text_input, "import_script_path").input(str(script))
    element_by_key(at.button, "import_script_button").click().run(timeout=20)
    assert not at.exception
    element_by_key(at.text_input, "import_voice_folder").input(str(voice_folder))
    element_by_key(at.button, "import_voice_button").click().run(timeout=20)
    assert not at.exception

    element_by_key(at.radio, "main_navigation").set_value("Shot Manager").run(timeout=20)
    assert not at.exception
    assert any(header.value == "Shot Manager" for header in at.header)
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

    verify_engine = create_db_engine(database_url)
    with verify_engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(Series)) == 1
        assert connection.scalar(select(func.count()).select_from(Episode)) == 1
        assert connection.scalar(select(func.count()).select_from(Shot)) == 2
        assert connection.scalar(select(func.count()).select_from(Asset)) == 2
    verify_engine.dispose()


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
