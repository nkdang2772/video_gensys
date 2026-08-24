from __future__ import annotations

import json
import os
import random
import sqlite3
import time
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.models import Job
from app.queue.job import PRIORITY_ORDER

_PRIORITY_SQL = "CASE priority " + " ".join(
    f"WHEN '{priority}' THEN {rank}" for rank, priority in enumerate(PRIORITY_ORDER)
) + f" ELSE {len(PRIORITY_ORDER)} END"


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    id: int
    episode_id: int
    shot_id: int | None
    job_type: str
    priority: str
    payload: dict[str, Any] | None
    attempt_count: int
    max_attempts: int
    worker_pid: int


def _is_locked_error(exc: BaseException) -> bool:
    error_code = getattr(exc, "sqlite_errorcode", None)
    if error_code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
        return True
    message = str(exc).lower()
    return "database is locked" in message or "database table is locked" in message


def _retry_delay(attempt: int, base_delay: float, jitter: float) -> float:
    return base_delay * (2**attempt) + random.uniform(0.0, jitter)


def _sqlite_utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")


def _load_claimed_job(engine: Engine, job_id: int, worker_pid: int) -> ClaimedJob:
    with Session(engine) as session:
        job = session.get(Job, job_id)
        if job is None:
            raise RuntimeError(f"Claimed Job disappeared: {job_id}")
        payload = dict(job.input_payload_json) if job.input_payload_json is not None else None
        return ClaimedJob(
            id=job.id,
            episode_id=job.episode_id,
            shot_id=job.shot_id,
            job_type=job.job_type,
            priority=job.priority,
            payload=payload,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
            worker_pid=worker_pid,
        )


def claim_next_job(
    engine: Engine,
    *,
    worker_pid: int | None = None,
    job_types: Collection[str] | None = None,
    max_busy_retries: int = 6,
    base_delay: float = 0.01,
    jitter: float = 0.01,
) -> ClaimedJob | None:
    """Atomically claim one queued job using a fresh connection per attempt."""
    if engine.dialect.name != "sqlite":
        raise ValueError("The local worker currently requires SQLite")
    if max_busy_retries < 0 or base_delay < 0 or jitter < 0:
        raise ValueError("Retry settings cannot be negative")
    pid = worker_pid if worker_pid is not None else os.getpid()
    selected_types = (
        (job_types,) if isinstance(job_types, str) else tuple(dict.fromkeys(job_types or ()))
    )
    if any(not item.strip() for item in selected_types):
        raise ValueError("job_types cannot contain an empty value")

    type_clause = ""
    type_parameters: tuple[Any, ...] = ()
    if selected_types:
        placeholders = ", ".join("?" for _ in selected_types)
        type_clause = f" AND job_type IN ({placeholders})"
        type_parameters = selected_types

    for attempt in range(max_busy_retries + 1):
        connection = engine.raw_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                "SELECT id FROM job WHERE status = 'queued'"
                + type_clause
                + f" ORDER BY {_PRIORITY_SQL}, created_at, id LIMIT 1",
                type_parameters,
            )
            row = cursor.fetchone()
            if row is None:
                connection.commit()
                return None
            job_id = int(row[0])
            cursor.execute(
                "UPDATE job SET status = 'running', worker_pid = ?, started_at = ?, "
                "completed_at = NULL, error_message = NULL WHERE id = ? AND status = 'queued'",
                (pid, _sqlite_utc_timestamp(), job_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"Atomic claim failed for Job {job_id}")
            connection.commit()
        except sqlite3.OperationalError as exc:
            connection.rollback()
            if not _is_locked_error(exc) or attempt >= max_busy_retries:
                raise
            time.sleep(_retry_delay(attempt, base_delay, jitter))
            continue
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()
        return _load_claimed_job(engine, job_id, pid)
    raise AssertionError("Unreachable busy-retry state")


def mark_job_done(
    engine: Engine, job_id: int, output_payload: Mapping[str, Any] | None = None
) -> None:
    payload = dict(output_payload) if output_payload is not None else None
    json.dumps(payload, allow_nan=False)
    with Session(engine) as session, session.begin():
        job = session.get(Job, job_id)
        if job is None or job.status != "running":
            raise RuntimeError(f"Job {job_id} is not running")
        job.status = "done"
        job.progress_percent = 100.0
        job.output_payload_json = payload
        job.completed_at = datetime.now(timezone.utc)
        job.worker_pid = None


def mark_job_failed(engine: Engine, job_id: int, error: str) -> None:
    with Session(engine) as session, session.begin():
        job = session.get(Job, job_id)
        if job is None or job.status != "running":
            raise RuntimeError(f"Job {job_id} is not running")
        job.status = "failed"
        job.attempt_count += 1
        job.error_message = error
        job.completed_at = datetime.now(timezone.utc)
        job.worker_pid = None


def requeue_failed_job(engine: Engine, job_id: int) -> bool:
    with Session(engine) as session, session.begin():
        job = session.get(Job, job_id)
        if job is None or job.status != "failed" or job.attempt_count >= job.max_attempts:
            return False
        job.status = "queued"
        job.progress_percent = 0.0
        job.worker_pid = None
        job.started_at = None
        job.completed_at = None
        return True


def run_worker(
    engine: Engine,
    handler: Callable[[ClaimedJob], Mapping[str, Any] | None],
    *,
    worker_pid: int | None = None,
    job_types: Collection[str] | None = None,
    poll_interval: float = 1.0,
    stop_event: Event | None = None,
    exit_when_empty: bool = False,
    max_jobs: int | None = None,
    retry_exceptions: tuple[type[Exception], ...] = (),
) -> int:
    """Poll, claim, and process jobs; processing occurs after the claim commit."""
    if poll_interval < 0:
        raise ValueError("poll_interval cannot be negative")
    if max_jobs is not None and max_jobs < 0:
        raise ValueError("max_jobs cannot be negative")
    stop = stop_event or Event()
    processed = 0
    while not stop.is_set() and (max_jobs is None or processed < max_jobs):
        claimed = claim_next_job(engine, worker_pid=worker_pid, job_types=job_types)
        if claimed is None:
            if exit_when_empty:
                break
            stop.wait(poll_interval)
            continue
        try:
            output = handler(claimed)
            mark_job_done(engine, claimed.id, output)
        except Exception as exc:
            mark_job_failed(engine, claimed.id, f"{type(exc).__name__}: {exc}")
            if isinstance(exc, retry_exceptions):
                requeue_failed_job(engine, claimed.id)
        processed += 1
    return processed
