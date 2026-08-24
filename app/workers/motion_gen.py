from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.media.ffprobe import probe_video
from app.models import Asset, Episode, Job, Shot
from app.motion.fallback import render_with_fallback
from app.motion.fill import apply_fill_policy
from app.paths import resolve, to_relative
from app.providers.video import VeoVideoProvider, VideoProvider, WanVideoProvider
from app.queue.worker import ClaimedJob, run_worker

SAFE_SHOT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def default_video_providers() -> dict[str, VideoProvider]:
    return {"wan_local": WanVideoProvider(), "veo_cloud": VeoVideoProvider()}


def _existing_asset(session: Session, job_id: int) -> Asset | None:
    return session.scalar(
        select(Asset).where(Asset.asset_type == "video", Asset.workflow_id == f"job:{job_id}")
    )


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_motion_job(
    engine: Engine,
    claimed: ClaimedJob,
    *,
    providers: Mapping[str, VideoProvider] | None = None,
) -> dict[str, Any]:
    if claimed.job_type != "motion_gen" or claimed.shot_id is None:
        raise ValueError("Motion worker only accepts shot-scoped motion_gen jobs")
    registry = dict(default_video_providers() if providers is None else providers)
    with Session(engine) as session:
        existing = _existing_asset(session, claimed.id)
        if existing is not None:
            return {"asset_id": existing.id, "file_path": existing.file_path, "reused": True}
        job = session.get(Job, claimed.id)
        shot = session.get(Shot, claimed.shot_id)
        episode = session.get(Episode, claimed.episode_id)
        if job is None or shot is None or episode is None or shot.episode_id != episode.id:
            raise ValueError("Motion Job references missing or inconsistent records")
        payload = dict(job.input_payload_json or {})
        provider_name = str(payload.get("provider") or "").lower()
        provider = registry.get(provider_name)
        if provider is None:
            raise ValueError(f"Motion provider is unavailable: {provider_name}")
        source_asset = session.get(Asset, payload.get("source_image_asset_id"))
        if (
            source_asset is None
            or source_asset.shot_id != shot.id
            or source_asset.asset_type != "image"
        ):
            raise ValueError("Motion Job source image is missing or belongs to another Shot")
        source_image = resolve(episode, source_asset.file_path)
        if not source_image.is_file():
            raise ValueError(f"Motion source image is missing: {source_image}")
        if not SAFE_SHOT_ID.fullmatch(shot.shot_id):
            raise ValueError(f"Unsafe shot_id for motion filename: {shot.shot_id!r}")
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("Motion Job has no prompt")
        config = dict(payload.get("config") or {})
        policy = str(payload.get("motion_fill_policy") or "extend")
        effective_duration = float(payload.get("effective_duration_sec") or config.get("fallback_duration_sec") or 5.0)
        temporary = resolve(episode, f"clips/generated/.jobs/job_{claimed.id}.mp4")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        model = str(config.get("model")) if config.get("model") is not None else None
        seed = int(config["seed"]) if config.get("seed") is not None else None
    result = render_with_fallback(
        provider,
        source_image,
        prompt,
        temporary,
        config,
        max_generative_attempts=int(config.get("max_generative_attempts", 3)),
        kenburns_config={
            "duration": effective_duration,
            "fps": float(config.get("fps", episode.effective_fps)),
            "ffmpeg_path": config.get("ffmpeg_path"),
            "timeout_sec": float(config.get("ffmpeg_timeout_sec", 300.0)),
        },
    )
    split_payload: list[dict[str, Any]] = []
    metadata = probe_video(result.output_path, ffprobe_path=config.get("ffprobe_path"))
    if result.method != "internal_kenburns" and (
        policy == "split" or abs(metadata.duration_sec - effective_duration) > 0.5 / metadata.frame_rate
    ):
        filled_path = temporary.with_name(f"job_{claimed.id}_filled.mp4")
        fill = apply_fill_policy(
            result.output_path,
            effective_duration,
            policy,
            output_path=filled_path,
            shot_id=shot.shot_id,
            max_segment_duration_sec=config.get("split_segment_duration_sec"),
            ffmpeg_path=config.get("ffmpeg_path"),
            ffprobe_path=config.get("ffprobe_path"),
        )
        if fill.output_path is not None:
            result.output_path.unlink(missing_ok=True)
            fill.output_path.replace(temporary)
        split_payload = [
            {
                "shot_id": item.shot_id,
                "start_sec": item.start_sec,
                "end_sec": item.end_sec,
                "duration_sec": item.duration_sec,
            }
            for item in fill.subshots
        ]
        metadata = probe_video(temporary, ffprobe_path=config.get("ffprobe_path"))
    cost = provider.cost(config)
    final_path: Path | None = None
    try:
        with Session(engine) as session, session.begin():
            existing = _existing_asset(session, claimed.id)
            if existing is not None:
                temporary.unlink(missing_ok=True)
                return {"asset_id": existing.id, "file_path": existing.file_path, "reused": True}
            shot = session.get(Shot, claimed.shot_id)
            episode = session.get(Episode, claimed.episode_id)
            job = session.get(Job, claimed.id)
            if shot is None or episode is None or job is None or job.status != "running":
                raise ValueError("Motion Job is no longer running")
            latest = session.scalar(
                select(func.max(Asset.version)).where(
                    Asset.shot_id == shot.id, Asset.asset_type == "video"
                )
            ) or 0
            version = latest + 1
            final_path = resolve(
                episode, f"clips/generated/{shot.shot_id}_motion_v{version:02d}.mp4"
            )
            if final_path.exists():
                raise ValueError(f"Motion version file already exists: {final_path}")
            shutil.copy2(temporary, final_path)
            asset = Asset(
                episode_id=episode.id,
                shot_id=shot.id,
                asset_type="video",
                version=version,
                is_chosen=False,
                provider=result.method,
                model=model,
                prompt=prompt,
                seed=seed,
                workflow_id=f"job:{claimed.id}",
                source_path=source_asset.file_path,
                file_path=to_relative(episode, final_path),
                width=metadata.width,
                height=metadata.height,
                duration_sec=metadata.duration_sec,
                frame_rate=metadata.frame_rate,
                codec=metadata.codec,
                file_size=final_path.stat().st_size,
                checksum=_checksum(final_path),
            )
            session.add(asset)
            job.provider = provider_name
            job.cost_usd = cost.usd
            job.cost_credit_amount = cost.credit_amount
            job.cost_credit_type = cost.credit_type
            job.cost_is_estimated = cost.is_estimated
            session.flush()
            asset_id = asset.id
            relative = asset.file_path
        temporary.unlink(missing_ok=True)
        return {
            "asset_id": asset_id,
            "file_path": relative,
            "provider_result": result.method,
            "generative_attempts": result.generative_attempts,
            "fallback_errors": list(result.errors),
            "subshots": split_payload,
            "reused": False,
        }
    except Exception:
        if final_path is not None:
            final_path.unlink(missing_ok=True)
        raise


def run_motion_worker(
    engine: Engine,
    *,
    providers: Mapping[str, VideoProvider] | None = None,
    exit_when_empty: bool = False,
    max_jobs: int | None = None,
) -> int:
    registry = dict(default_video_providers() if providers is None else providers)

    def handler(claimed: ClaimedJob) -> dict[str, Any]:
        return process_motion_job(engine, claimed, providers=registry)

    return run_worker(
        engine,
        handler,
        job_types={"motion_gen"},
        exit_when_empty=exit_when_empty,
        max_jobs=max_jobs,
    )
