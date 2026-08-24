from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Job

DEFAULT_STALE_TIMEOUT = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    stale_job_ids: tuple[int, ...]
    requeued_job_ids: tuple[int, ...]


def recover_stale_jobs(
    session: Session,
    *,
    timeout: timedelta = DEFAULT_STALE_TIMEOUT,
    now: datetime | None = None,
) -> RecoveryResult:
    if timeout.total_seconds() <= 0:
        raise ValueError("timeout must be positive")
    recovery_time = now or datetime.now(timezone.utc)
    if recovery_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    stale_before = recovery_time - timeout

    stale_jobs = list(
        session.scalars(
            select(Job).where(
                Job.status == "running",
                Job.started_at.is_not(None),
                Job.started_at < stale_before,
            )
        )
    )
    stale_ids: list[int] = []
    for job in stale_jobs:
        job.status = "failed"
        job.error_message = "stale"
        job.attempt_count += 1
        job.worker_pid = None
        job.completed_at = recovery_time
        stale_ids.append(job.id)
    session.flush()

    retryable_jobs = list(
        session.scalars(
            select(Job)
            .where(Job.status == "failed", Job.attempt_count < Job.max_attempts)
            .order_by(Job.created_at, Job.id)
        )
    )
    requeued_ids: list[int] = []
    for job in retryable_jobs:
        job.status = "queued"
        job.progress_percent = 0.0
        job.worker_pid = None
        job.started_at = None
        job.completed_at = None
        requeued_ids.append(job.id)
    session.flush()
    return RecoveryResult(tuple(stale_ids), tuple(requeued_ids))
