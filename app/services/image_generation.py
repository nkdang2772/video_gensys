from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.models import Asset, Episode, EpisodeReferencePin, Job, Reference, ReferenceVersion, Shot
from app.queue.job import enqueue

IMAGE_PROVIDERS = frozenset({"google", "comfyui", "manual"})


def pinned_versions_for_shot(
    session: Session,
    shot: Shot,
    *,
    explicit_version_ids: Sequence[int] | None = None,
) -> list[ReferenceVersion]:
    statement = (
        select(ReferenceVersion)
        .join(EpisodeReferencePin, EpisodeReferencePin.reference_version_id == ReferenceVersion.id)
        .join(Reference, Reference.id == EpisodeReferencePin.reference_id)
        .where(EpisodeReferencePin.episode_id == shot.episode_id)
    )
    if explicit_version_ids is not None:
        requested = set(explicit_version_ids)
        versions = list(session.scalars(statement.where(ReferenceVersion.id.in_(requested))))
        if {version.id for version in versions} != requested:
            raise ValueError("One or more requested reference versions are not pinned to the Episode")
        return sorted(versions, key=lambda version: version.id)
    character_ids = set(shot.characters_json or [])
    statement = statement.where(
        or_(
            Reference.reference_type == "style",
            Reference.slug.in_(character_ids),
            Reference.id == shot.location_reference_id,
        )
    )
    return list(session.scalars(statement.order_by(ReferenceVersion.id)))


def enqueue_image_job(
    session: Session,
    *,
    shot_id: int,
    provider: str,
    config: Mapping[str, Any] | None = None,
    prompt: str | None = None,
    negative_prompt: str | None = None,
    priority: str = "image",
    max_attempts: int = 3,
) -> Job:
    clean_provider = provider.strip().lower()
    if clean_provider not in IMAGE_PROVIDERS:
        raise ValueError(f"Unsupported image provider: {provider}")
    shot = session.get(Shot, shot_id)
    if shot is None:
        raise ValueError(f"Shot not found: {shot_id}")
    versions = pinned_versions_for_shot(session, shot)
    effective_prompt = (prompt if prompt is not None else shot.image_prompt or shot.visual_description or "").strip()
    if not effective_prompt:
        raise ValueError(f"Shot {shot.shot_id} has no image prompt or visual description")
    payload = {
        "provider": clean_provider,
        "prompt": effective_prompt,
        "negative_prompt": negative_prompt if negative_prompt is not None else shot.negative_prompt,
        "config": dict(config or {}),
        "reference_version_ids": [version.id for version in versions],
        "character_batch_key": shot.character_batch_key,
    }
    return enqueue(
        session,
        job_type="image_gen",
        priority=priority,
        payload=payload,
        episode_id=shot.episode_id,
        shot_id=shot.id,
        max_attempts=max_attempts,
    )


def enqueue_character_batch(
    session: Session,
    *,
    episode_id: int,
    provider: str,
    config: Mapping[str, Any] | None = None,
) -> list[Job]:
    if session.get(Episode, episode_id) is None:
        raise ValueError(f"Episode not found: {episode_id}")
    has_image = exists().where(Asset.shot_id == Shot.id, Asset.asset_type == "image")
    active_job = exists().where(
        Job.shot_id == Shot.id,
        Job.job_type == "image_gen",
        Job.status.in_(("queued", "running")),
    )
    shots = list(
        session.scalars(
            select(Shot).where(
                Shot.episode_id == episode_id,
                ~has_image,
                ~active_job,
            )
        )
    )
    sortable: list[tuple[str, tuple[int, ...], int, Shot]] = []
    for shot in shots:
        version_ids = tuple(version.id for version in pinned_versions_for_shot(session, shot))
        sortable.append((shot.character_batch_key or "", version_ids, shot.order_index, shot))
    jobs: list[Job] = []
    for _batch_key, _version_ids, _order, shot in sorted(sortable, key=lambda item: item[:3]):
        jobs.append(
            enqueue_image_job(
                session,
                shot_id=shot.id,
                provider=provider,
                config=config,
                priority="overnight",
            )
        )
    return jobs


def choose_image_asset(session: Session, asset_id: int) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None or asset.asset_type != "image" or asset.shot_id is None:
        raise ValueError(f"Image Asset not found: {asset_id}")
    selected = list(
        session.scalars(
            select(Asset).where(
                Asset.shot_id == asset.shot_id,
                Asset.asset_type == "image",
                Asset.is_chosen.is_(True),
                Asset.id != asset.id,
            )
        )
    )
    for previous in selected:
        previous.is_chosen = False
    session.flush()
    asset.is_chosen = True
    session.flush()
    return asset
