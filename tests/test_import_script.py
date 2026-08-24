from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import Episode, Scene, Shot
from app.parsers.script_txt import parse_text
from app.services.import_script import ScriptImportError, import_parsed_script
from app.services.series import create_series


def create_episode_record(session, root: Path) -> Episode:
    series = create_series(session, name="Generic Series")
    root.mkdir(parents=True)
    (root / "script").mkdir()
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


def test_import_parsed_script_creates_scenes_shots_and_source_copy(session, tmp_path: Path) -> None:
    episode = create_episode_record(session, tmp_path / "episode")
    content = """[SCENE: Opening]
[SHOT: s001]
[TEXT: First line]
[VISUAL: First visual]
[MOTION_INTENT: pan]
[SHOT: s002]
[TEXT: Second line]
[VISUAL: Second visual]
[SCENE: Closing]
[SHOT: s003]
[TEXT: Third line]
[VISUAL: Third visual]
"""
    parsed = parse_text(content)
    shots = import_parsed_script(
        session,
        episode_id=episode.id,
        parsed_shots=parsed,
        source_name="generic_script.txt",
        source_bytes=content.encode(),
    )
    assert len(shots) == 3
    assert session.scalar(select(func.count()).select_from(Scene)) == 2
    assert session.scalar(select(func.count()).select_from(Shot)) == 3
    assert (Path(episode.root_path) / "script" / "generic_script.txt").read_text() == content


def test_second_script_import_rolls_back_without_overwriting_source(session, tmp_path: Path) -> None:
    episode = create_episode_record(session, tmp_path / "episode")
    parsed = parse_text("[SHOT: s001]\n[TEXT: First]")
    import_parsed_script(
        session,
        episode_id=episode.id,
        parsed_shots=parsed,
        source_name="first.txt",
        source_bytes=b"first",
    )
    with pytest.raises(ScriptImportError, match="already contains shots"):
        import_parsed_script(
            session,
            episode_id=episode.id,
            parsed_shots=parse_text("[SHOT: s002]\n[TEXT: Second]"),
            source_name="second.txt",
            source_bytes=b"second",
        )
    assert not (Path(episode.root_path) / "script" / "second.txt").exists()
    assert session.scalar(select(func.count()).select_from(Shot)) == 1
