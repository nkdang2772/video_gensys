from __future__ import annotations

import copy
import shutil
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Episode, EpisodeReferencePin, Reference, ReferenceVersion, Series
from app.services.errors import EpisodeCreationError, ReferencePinError, SeriesNotFoundError
from app.services.series import slugify

EPISODE_DIRECTORIES = (
    "script",
    "audio/source",
    "audio/segments",
    "audio/normalized",
    "images/generated",
    "images/chosen",
    "images/upscaled",
    "clips/generated",
    "clips/chosen",
    "clips/normalized",
    "proxies",
    "qa",
    "export",
)


def _create_episode_folder_tree(root: Path) -> None:
    for relative_path in EPISODE_DIRECTORIES:
        (root / Path(relative_path)).mkdir(parents=True, exist_ok=False)


def _reference_version_for_pin(session: Session, reference: Reference) -> ReferenceVersion:
    if reference.current_version <= 0:
        raise ReferencePinError(
            f"Reference {reference.slug!r} has no current version and cannot be pinned"
        )
    version = session.scalar(
        select(ReferenceVersion).where(
            ReferenceVersion.reference_id == reference.id,
            ReferenceVersion.version == reference.current_version,
        )
    )
    if version is None:
        raise ReferencePinError(
            f"Current version {reference.current_version} is missing for reference {reference.slug!r}"
        )
    return version


def _references_to_pin(
    session: Session, series: Series, shared_reference_ids: Iterable[int]
) -> list[Reference]:
    references = list(
        session.scalars(
            select(Reference).where(
                Reference.owning_series_id == series.id,
                Reference.scope == "series_specific",
                Reference.is_active.is_(True),
            )
        )
    )
    by_id = {reference.id: reference for reference in references}

    if series.style_anchor_reference_id is not None:
        style_anchor = session.get(Reference, series.style_anchor_reference_id)
        if style_anchor is None:
            raise ReferencePinError("The configured style anchor reference does not exist")
        by_id[style_anchor.id] = style_anchor

    selected_ids = set(shared_reference_ids)
    if selected_ids:
        selected = list(
            session.scalars(
                select(Reference).where(
                    Reference.id.in_(selected_ids),
                    Reference.scope == "shared_across_series",
                    Reference.is_active.is_(True),
                )
            )
        )
        if {reference.id for reference in selected} != selected_ids:
            raise ReferencePinError("One or more selected shared references are invalid or inactive")
        by_id.update({reference.id: reference for reference in selected})
    return [by_id[reference_id] for reference_id in sorted(by_id)]


def create_episode(
    session: Session,
    *,
    series_id: int,
    episode_number: int,
    title: str,
    library_root: str | Path,
    slug: str | None = None,
    target_duration_sec: float | None = None,
    shared_reference_ids: Iterable[int] = (),
) -> Episode:
    if session.in_transaction():
        raise EpisodeCreationError("create_episode requires a Session without an active transaction")
    if episode_number <= 0:
        raise ValueError("episode_number must be positive")
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Episode title cannot be empty")
    clean_slug = slugify(slug or clean_title)

    episode_root: Path | None = None
    folder_created = False
    try:
        with session.begin():
            series = session.scalar(
                select(Series).where(Series.id == series_id, Series.deleted_at.is_(None))
            )
            if series is None:
                raise SeriesNotFoundError(f"Series not found: {series_id}")

            folder_name = f"ep_{episode_number:02d}_{clean_slug}"
            episode_root = (
                Path(library_root).expanduser().resolve()
                / "series"
                / series.slug
                / "episodes"
                / folder_name
            )
            episode_root.mkdir(parents=True, exist_ok=False)
            folder_created = True
            _create_episode_folder_tree(episode_root)

            references = _references_to_pin(session, series, shared_reference_ids)
            versions = {
                reference.id: _reference_version_for_pin(session, reference)
                for reference in references
            }
            style_version = (
                versions[series.style_anchor_reference_id].version
                if series.style_anchor_reference_id in versions
                else None
            )

            episode = Episode(
                series=series,
                episode_number=episode_number,
                slug=clean_slug,
                title=clean_title,
                status="draft",
                effective_resolution=series.default_resolution,
                effective_fps=series.default_fps,
                effective_aspect_ratio=series.default_aspect_ratio,
                style_anchor_version_snapshot=style_version,
                palette_snapshot_json=copy.deepcopy(series.palette_json),
                font_config_snapshot_json=copy.deepcopy(series.font_config_json),
                target_duration_sec=target_duration_sec,
                root_path=str(episode_root),
            )
            session.add(episode)
            session.flush()
            session.add_all(
                EpisodeReferencePin(
                    episode=episode,
                    reference=reference,
                    reference_version=versions[reference.id],
                )
                for reference in references
            )
            session.flush()
        return episode
    except Exception as exc:
        if folder_created and episode_root is not None and episode_root.exists():
            try:
                shutil.rmtree(episode_root)
            except OSError as cleanup_error:
                raise EpisodeCreationError(
                    f"Episode creation failed and folder cleanup also failed: {episode_root}"
                ) from cleanup_error
        if isinstance(exc, (EpisodeCreationError, SeriesNotFoundError, ValueError)):
            raise
        raise EpisodeCreationError(f"Could not create episode: {exc}") from exc

