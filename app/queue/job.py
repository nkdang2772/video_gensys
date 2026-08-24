from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models import Episode, Job, Shot

PRIORITY_ORDER = ("high", "normal", "image", "gpu", "overnight", "export")
VALID_PRIORITIES = frozenset(PRIORITY_ORDER)
_PRIORITY_RANK = case(
    {priority: rank for rank, priority in enumerate(PRIORITY_ORDER)},
    value=Job.priority,
    else_=len(PRIORITY_ORDER),
)


class JobNotFoundError(LookupError):
    """Raised when a queue operation targets a missing job."""


def enqueue(
    session: Session,
    *,
    job_type: str,
    priority: str = "normal",
    payload: Mapping[str, Any] | None = None,
    episode_id: int,
    shot_id: int | None = None,
    max_attempts: int = 3,
) -> Job:
    clean_job_type = job_type.strip()
    if not clean_job_type:
        raise ValueError("job_type cannot be empty")
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Unsupported job priority: {priority}")
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    if session.get(Episode, episode_id) is None:
        raise ValueError(f"Episode not found: {episode_id}")
    if shot_id is not None:
        matching_shot = session.scalar(
            select(Shot.id).where(Shot.id == shot_id, Shot.episode_id == episode_id)
        )
        if matching_shot is None:
            raise ValueError(f"Shot {shot_id} does not belong to Episode {episode_id}")

    clean_payload = dict(payload) if payload is not None else None
    try:
        json.dumps(clean_payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("payload must be JSON serializable") from exc

    job = Job(
        episode_id=episode_id,
        shot_id=shot_id,
        job_type=clean_job_type,
        priority=priority,
        status="queued",
        input_payload_json=clean_payload,
        max_attempts=max_attempts,
    )
    session.add(job)
    session.flush()
    return job


def get_status(session: Session, job_id: int) -> str:
    status = session.scalar(select(Job.status).where(Job.id == job_id))
    if status is None:
        raise JobNotFoundError(f"Job not found: {job_id}")
    return status


def list_queued(
    session: Session,
    *,
    episode_id: int | None = None,
    job_type: str | None = None,
) -> list[Job]:
    statement = select(Job).where(Job.status == "queued")
    if episode_id is not None:
        statement = statement.where(Job.episode_id == episode_id)
    if job_type is not None:
        statement = statement.where(Job.job_type == job_type)
    statement = statement.order_by(_PRIORITY_RANK, Job.created_at, Job.id)
    return list(session.scalars(statement))
