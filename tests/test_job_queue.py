from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import Episode, Job, Series, Shot
from app.queue.job import JobNotFoundError, enqueue, get_status, list_queued
from app.queue.recovery import recover_stale_jobs
from app.queue.worker import claim_next_job, run_worker


def _create_episode(session: Session, tmp_path, *, suffix: str = "main") -> Episode:
    series = Series(slug=f"series-{suffix}", name=f"Series {suffix}")
    episode = Episode(
        series=series,
        episode_number=1,
        slug=f"episode-{suffix}",
        title=f"Episode {suffix}",
        effective_resolution="1920x1080",
        effective_fps=30,
        effective_aspect_ratio="16:9",
        root_path=str(tmp_path / suffix),
    )
    session.add(episode)
    session.flush()
    return episode


def test_enqueue_status_and_priority_order(session, tmp_path) -> None:
    episode = _create_episode(session, tmp_path)
    priorities = ("export", "normal", "high", "gpu", "image")
    jobs = [
        enqueue(
            session,
            job_type="generic_task",
            priority=priority,
            payload={"position": position},
            episode_id=episode.id,
        )
        for position, priority in enumerate(priorities)
    ]
    session.commit()

    assert [job.priority for job in list_queued(session)] == [
        "high",
        "normal",
        "image",
        "gpu",
        "export",
    ]
    assert get_status(session, jobs[0].id) == "queued"

    try:
        get_status(session, 999_999)
    except JobNotFoundError:
        pass
    else:
        raise AssertionError("Missing jobs must raise JobNotFoundError")


def test_enqueue_rejects_shot_from_another_episode(session, tmp_path) -> None:
    first = _create_episode(session, tmp_path, suffix="first")
    second = _create_episode(session, tmp_path, suffix="second")
    shot = Shot(episode=second, shot_id="s001", order_index=1)
    session.add(shot)
    session.flush()

    try:
        enqueue(
            session,
            job_type="generic_task",
            episode_id=first.id,
            shot_id=shot.id,
        )
    except ValueError as exc:
        assert "does not belong" in str(exc)
    else:
        raise AssertionError("Cross-episode shot references must be rejected")


def test_two_workers_claim_each_job_exactly_once(engine, tmp_path) -> None:
    with Session(engine) as session, session.begin():
        episode = _create_episode(session, tmp_path)
        for number in range(20):
            enqueue(
                session,
                job_type="parallel_task",
                priority="normal" if number % 2 else "high",
                payload={"number": number},
                episode_id=episode.id,
            )

    claimed_ids: list[int] = []
    claimed_by_worker: dict[int, list[int]] = {41001: [], 41002: []}
    lock = threading.Lock()
    start = threading.Barrier(2)

    def worker(worker_pid: int) -> int:
        start.wait(timeout=5)

        def handler(job):
            with lock:
                claimed_ids.append(job.id)
                claimed_by_worker[worker_pid].append(job.id)
            time.sleep(0.002)
            return {"worker": worker_pid}

        return run_worker(
            engine,
            handler,
            worker_pid=worker_pid,
            job_types={"parallel_task"},
            exit_when_empty=True,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        processed = list(executor.map(worker, (41001, 41002)))

    assert sum(processed) == 20
    assert len(claimed_ids) == 20
    assert len(set(claimed_ids)) == 20
    assert all(claimed_by_worker.values())
    with Session(engine) as session:
        jobs = list(session.scalars(select(Job).order_by(Job.id)))
        assert [job.status for job in jobs] == ["done"] * 20
        assert all(job.worker_pid is None for job in jobs)


def test_claim_retries_after_sqlite_busy(engine, session, tmp_path, monkeypatch) -> None:
    episode = _create_episode(session, tmp_path)
    queued = enqueue(session, job_type="locked_task", episode_id=episode.id)
    session.commit()
    queued_id = queued.id
    session.close()

    def set_short_busy_timeout(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA busy_timeout=1")

    engine.dispose()
    event.listen(engine, "connect", set_short_busy_timeout)
    locker = engine.raw_connection()
    locker.execute("BEGIN IMMEDIATE")
    retry_observed = threading.Event()
    release_retry = threading.Event()

    def controlled_sleep(_delay: float) -> None:
        retry_observed.set()
        assert release_retry.wait(timeout=5)

    monkeypatch.setattr("app.queue.worker.time.sleep", controlled_sleep)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            claim_next_job,
            engine,
            worker_pid=41500,
            max_busy_retries=2,
            base_delay=0.001,
            jitter=0,
        )
        assert retry_observed.wait(timeout=5)
        locker.commit()
        locker.close()
        release_retry.set()
        claimed = future.result(timeout=5)

    assert claimed is not None and claimed.id == queued_id


def test_invalid_handler_output_marks_job_failed(engine, tmp_path) -> None:
    with Session(engine) as session, session.begin():
        episode = _create_episode(session, tmp_path)
        job = enqueue(session, job_type="invalid_output", episode_id=episode.id)
        job_id = job.id

    processed = run_worker(
        engine,
        lambda _job: {"invalid": {object()}},
        exit_when_empty=True,
    )

    assert processed == 1
    with Session(engine) as session:
        failed = session.get(Job, job_id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.attempt_count == 1
        assert "not JSON serializable" in (failed.error_message or "")


def test_stale_running_job_is_requeued_for_retry(engine, tmp_path) -> None:
    with Session(engine) as session, session.begin():
        episode = _create_episode(session, tmp_path)
        job = enqueue(
            session,
            job_type="recoverable_task",
            episode_id=episode.id,
            max_attempts=3,
        )
        job_id = job.id

    claimed = claim_next_job(engine, worker_pid=42001)
    assert claimed is not None and claimed.id == job_id
    recovery_time = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        running_job = session.get(Job, job_id)
        assert running_job is not None
        running_job.started_at = recovery_time - timedelta(minutes=31)

    with Session(engine) as session, session.begin():
        result = recover_stale_jobs(session, now=recovery_time)
        assert result.stale_job_ids == (job_id,)
        assert result.requeued_job_ids == (job_id,)

    with Session(engine) as session:
        recovered = session.get(Job, job_id)
        assert recovered is not None
        assert recovered.status == "queued"
        assert recovered.attempt_count == 1
        assert recovered.error_message == "stale"
        assert recovered.worker_pid is None
        assert recovered.started_at is None
    claimed_again = claim_next_job(engine, worker_pid=42002)
    assert claimed_again is not None and claimed_again.id == job_id


def test_stale_job_at_attempt_limit_remains_failed(engine, tmp_path) -> None:
    now = datetime.now(timezone.utc)
    with Session(engine) as session, session.begin():
        episode = _create_episode(session, tmp_path)
        job = enqueue(
            session,
            job_type="limited_task",
            episode_id=episode.id,
            max_attempts=1,
        )
        job.status = "running"
        job.worker_pid = 43001
        job.started_at = now - timedelta(hours=1)
        job_id = job.id

    with Session(engine) as session, session.begin():
        result = recover_stale_jobs(session, now=now)
        assert result.stale_job_ids == (job_id,)
        assert result.requeued_job_ids == ()

    with Session(engine) as session:
        failed = session.get(Job, job_id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.attempt_count == 1
        assert failed.error_message == "stale"
