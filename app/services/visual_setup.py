from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Episode, Reference, Series, Shot
from app.parsers.dispatcher import parse_script_file
from app.services.episode import create_episode
from app.services.import_script import import_parsed_script
from app.services.prompt_catalog import import_prompt_catalog, parse_prompt_catalog
from app.services.reference_mapping import auto_map_episode_references
from app.services.series import create_series, slugify


@dataclass(frozen=True, slots=True)
class VisualSetupResult:
    series_id: int
    episode_id: int
    reference_count: int
    shot_count: int
    character_mapped: int
    location_mapped: int
    episode_root: Path


def prepare_visual_episode(
    session_factory: sessionmaker[Session],
    *,
    series_name: str,
    episode_title: str,
    episode_number: int,
    library_root: str | Path,
    script_path: str | Path,
    character_prompts_path: str | Path,
    background_prompts_path: str | Path,
    planned_duration_sec: float = 4.0,
) -> VisualSetupResult:
    """Idempotently prepare a visual-first Episode from the three production inputs."""
    script = Path(script_path).expanduser().resolve()
    character_prompts = Path(character_prompts_path).expanduser().resolve()
    background_prompts = Path(background_prompts_path).expanduser().resolve()
    parsed_shots = parse_script_file(script)
    catalog_entries = [
        *parse_prompt_catalog(
            character_prompts.read_text(encoding="utf-8-sig"), source=str(character_prompts)
        ),
        *parse_prompt_catalog(
            background_prompts.read_text(encoding="utf-8-sig"), source=str(background_prompts)
        ),
    ]
    series_slug = slugify(series_name)
    with session_factory() as session:
        series = session.scalar(
            select(Series).where(Series.slug == series_slug, Series.deleted_at.is_(None))
        )
        if series is None:
            series = create_series(session, name=series_name)
            session.commit()
        series_id = series.id

    with session_factory() as session:
        episode = session.scalar(
            select(Episode).where(
                Episode.series_id == series_id, Episode.episode_number == episode_number
            )
        )
        if episode is None:
            session.rollback()
            episode = create_episode(
                session,
                series_id=series_id,
                episode_number=episode_number,
                title=episode_title,
                library_root=library_root,
            )
        episode_id, episode_root = episode.id, Path(episode.root_path)

    with session_factory.begin() as session:
        references, _ = import_prompt_catalog(
            session, series_id=series_id, entries=catalog_entries
        )
        reference_count = len(references)

    with session_factory() as session:
        existing_shots = session.scalar(
            select(func.count()).select_from(Shot).where(Shot.episode_id == episode_id)
        ) or 0
        session.rollback()
        if existing_shots == 0:
            imported = import_parsed_script(
                session,
                episode_id=episode_id,
                parsed_shots=parsed_shots,
                source_name=script.name,
                source_bytes=script.read_bytes(),
                planned_duration_sec=planned_duration_sec,
            )
            shot_count = len(imported)
        elif existing_shots == len(parsed_shots):
            shot_count = existing_shots
        else:
            raise ValueError(
                f"Episode already has {existing_shots} shots; input contains {len(parsed_shots)}"
            )
    with session_factory.begin() as session:
        mapping = auto_map_episode_references(session, episode_id)
    return VisualSetupResult(
        series_id,
        episode_id,
        reference_count,
        shot_count,
        mapping.character_mapped,
        mapping.location_mapped,
        episode_root,
    )
