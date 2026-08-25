from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, Job, Shot
from app.queue.job import enqueue
from app.services.timing import effective_shot_duration

MOTION_PROVIDERS = frozenset({"wan_local", "veo_cloud"})


def enqueue_motion_job(
    session: Session,
    *,
    shot_id: int,
    provider: str,
    config: Mapping[str, Any] | None = None,
    prompt: str | None = None,
    source_image_asset_id: int | None = None,
    priority: str = "gpu",
    max_attempts: int = 3,
) -> Job:
    shot = session.get(Shot, shot_id)
    if shot is None:
        raise ValueError(f"Shot not found: {shot_id}")
    clean_provider = provider.strip().lower()
    if clean_provider not in MOTION_PROVIDERS:
        raise ValueError(f"Unsupported motion provider: {provider}")
    if source_image_asset_id is None:
        source = session.scalar(
            select(Asset).where(
                Asset.shot_id == shot.id,
                Asset.asset_type == "image",
                Asset.is_chosen.is_(True),
            )
        )
    else:
        source = session.get(Asset, source_image_asset_id)
    if source is None or source.shot_id != shot.id or source.asset_type != "image":
        raise ValueError(f"Shot {shot.shot_id} requires a chosen source image")
    effective_prompt = str(prompt or shot.visual_description or shot.image_prompt or "").strip()
    if not effective_prompt:
        raise ValueError(f"Shot {shot.shot_id} has no motion prompt")
    active = session.scalar(
        select(Job.id).where(
            Job.shot_id == shot.id,
            Job.job_type == "motion_gen",
            Job.status.in_(("queued", "running")),
        )
    )
    if active is not None:
        raise ValueError(f"Shot {shot.shot_id} already has an active motion job")
    payload = {
        "provider": clean_provider,
        "prompt": effective_prompt,
        "source_image_asset_id": source.id,
        "motion_fill_policy": shot.motion_fill_policy or "extend",
        "effective_duration_sec": effective_shot_duration(shot),
        "config": dict(config or {}),
    }
    job = enqueue(
        session,
        job_type="motion_gen",
        priority=priority,
        payload=payload,
        episode_id=shot.episode_id,
        shot_id=shot.id,
        max_attempts=max_attempts,
    )
    job.provider = clean_provider
    return job


def retry_motion_job(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if job is None or job.job_type != "motion_gen" or job.status != "failed":
        raise ValueError(f"Failed motion Job not found: {job_id}")
    job.status = "queued"
    job.progress_percent = 0.0
    job.attempt_count = 0
    job.error_message = None
    job.worker_pid = None
    job.started_at = None
    job.completed_at = None
    session.flush()
    return job


def choose_motion_asset(session: Session, asset_id: int) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None or asset.asset_type != "video" or asset.shot_id is None:
        raise ValueError(f"Motion Asset not found: {asset_id}")
    chosen = list(
        session.scalars(
            select(Asset).where(
                Asset.shot_id == asset.shot_id,
                Asset.asset_type == "video",
                Asset.is_chosen.is_(True),
                Asset.id != asset.id,
            )
        )
    )
    for previous in chosen:
        previous.is_chosen = False
    session.flush()
    asset.is_chosen = True
    session.flush()
    return asset
