from __future__ import annotations

import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.models import Asset, Episode, Job, Shot
from app.paths import resolve, to_relative
from app.providers.image import (
    ComfyUIImageProvider,
    GoogleFlowImageProvider,
    ImageProvider,
    ManualImageProvider,
    ProviderError,
    ProviderTimeoutError,
)
from app.providers.image.base import png_metadata
from app.queue.worker import ClaimedJob, run_worker
from app.services.image_generation import pinned_versions_for_shot
from app.services.reference import resolve_reference_file

SAFE_SHOT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def default_image_providers() -> dict[str, ImageProvider]:
    flow = GoogleFlowImageProvider()
    return {
        "google_flow": flow,
        "google": flow,
        "comfyui": ComfyUIImageProvider(),
        "manual": ManualImageProvider(),
    }


def _existing_asset(session: Session, job_id: int) -> Asset | None:
    return session.scalar(
        select(Asset).where(Asset.asset_type == "image", Asset.workflow_id == f"job:{job_id}")
    )


def process_image_job(
    engine: Engine,
    claimed: ClaimedJob,
    *,
    library_root: str | Path,
    providers: Mapping[str, ImageProvider] | None = None,
) -> dict[str, Any]:
    if claimed.job_type != "image_gen" or claimed.shot_id is None:
        raise ValueError("Image worker only accepts shot-scoped image_gen jobs")
    registry = dict(default_image_providers() if providers is None else providers)
    with Session(engine) as session:
        existing = _existing_asset(session, claimed.id)
        if existing is not None:
            return {"asset_id": existing.id, "file_path": existing.file_path, "reused": True}
        job = session.get(Job, claimed.id)
        shot = session.get(Shot, claimed.shot_id)
        episode = session.get(Episode, claimed.episode_id)
        if job is None or shot is None or episode is None or shot.episode_id != episode.id:
            raise ValueError("Image Job references missing or inconsistent records")
        payload = dict(job.input_payload_json or {})
        provider_name = str(payload.get("provider", "")).lower()
        if provider_name == "google":
            provider_name = "google_flow"
        provider = registry.get(provider_name)
        if provider is None:
            raise ProviderError(f"Image provider is unavailable: {provider_name}")
        prompt = str(payload.get("prompt") or shot.image_prompt or shot.visual_description or "").strip()
        if not prompt:
            raise ValueError("Image Job has no prompt")
        negative_prompt = payload.get("negative_prompt")
        config = dict(payload.get("config") or {})
        requested_versions = payload.get("reference_version_ids")
        if not isinstance(requested_versions, list) or any(
            not isinstance(item, int) for item in requested_versions
        ):
            raise ValueError("Image Job requires pinned reference_version_ids")
        versions = pinned_versions_for_shot(
            session, shot, explicit_version_ids=requested_versions
        )
        reference_paths = [resolve_reference_file(library_root, version) for version in versions]
        missing_references = [path for path in reference_paths if not path.is_file()]
        if missing_references:
            raise ProviderError(f"Pinned reference file is missing: {missing_references[0]}")
        if not SAFE_SHOT_ID.fullmatch(shot.shot_id):
            raise ValueError(f"Unsafe shot_id for image filename: {shot.shot_id!r}")
        temporary = resolve(episode, f"images/generated/.jobs/job_{claimed.id}.png")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        model = str(config.get("model")) if config.get("model") is not None else None
        seed = int(config["seed"]) if config.get("seed") is not None else None
    if not temporary.exists():
        provider_config = dict(config)
        provider_config["output_path"] = str(temporary)
        provider.generate(prompt, reference_paths, provider_config)
    width, height, file_size, checksum = png_metadata(temporary)
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
                raise ValueError("Image Job is no longer running")
            latest = session.scalar(
                select(func.max(Asset.version)).where(
                    Asset.shot_id == shot.id, Asset.asset_type == "image"
                )
            ) or 0
            version = latest + 1
            final_path = resolve(
                episode, f"images/generated/{shot.shot_id}_image_v{version:02d}.png"
            )
            if final_path.exists():
                raise ValueError(f"Image version file already exists: {final_path}")
            shutil.copy2(temporary, final_path)
            asset = Asset(
                episode_id=episode.id,
                shot_id=shot.id,
                asset_type="image",
                version=version,
                is_chosen=False,
                provider=provider_name,
                model=model,
                prompt=prompt,
                negative_prompt=str(negative_prompt) if negative_prompt is not None else None,
                seed=seed,
                workflow_id=f"job:{claimed.id}",
                file_path=to_relative(episode, final_path),
                width=width,
                height=height,
                file_size=file_size,
                checksum=checksum,
            )
            session.add(asset)
            session.flush()
            job.provider = provider_name
            job.cost_usd = cost.usd
            job.cost_credit_amount = cost.credit_amount
            job.cost_credit_type = cost.credit_type
            job.cost_is_estimated = cost.is_estimated
            asset_id = asset.id
            relative_path = asset.file_path
        temporary.unlink(missing_ok=True)
        return {"asset_id": asset_id, "file_path": relative_path, "reused": False}
    except Exception:
        if final_path is not None:
            final_path.unlink(missing_ok=True)
        raise


def run_image_worker(
    engine: Engine,
    *,
    library_root: str | Path,
    providers: Mapping[str, ImageProvider] | None = None,
    exit_when_empty: bool = False,
    max_jobs: int | None = None,
) -> int:
    registry = dict(default_image_providers() if providers is None else providers)

    def handler(claimed: ClaimedJob) -> dict[str, Any]:
        return process_image_job(
            engine,
            claimed,
            library_root=library_root,
            providers=registry,
        )

    return run_worker(
        engine,
        handler,
        job_types={"image_gen"},
        exit_when_empty=exit_when_empty,
        max_jobs=max_jobs,
        retry_exceptions=(ProviderTimeoutError,),
    )
