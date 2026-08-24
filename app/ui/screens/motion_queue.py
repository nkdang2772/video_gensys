from __future__ import annotations

from pathlib import Path

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, sessionmaker

from app.models import Asset, Job, Shot
from app.paths import resolve
from app.services.motion_generation import (
    choose_motion_asset,
    enqueue_motion_job,
    retry_motion_job,
)


def render(session_factory: sessionmaker[Session], library_root: Path) -> None:
    del library_root
    st.header("Motion Queue")
    episode_id = st.session_state.get("selected_episode_id")
    if episode_id is None:
        st.info("Open an Episode first.")
        return
    with session_factory() as session:
        shots = list(
            session.scalars(
                select(Shot)
                .options(joinedload(Shot.episode))
                .where(Shot.episode_id == episode_id)
                .order_by(Shot.order_index)
            )
        )
    if not shots:
        st.info("This Episode has no shots. Import a script first.")
        return
    options = {shot.shot_id: shot for shot in shots}
    selected_label = st.selectbox("Shot", list(options), key="motion_shot")
    shot = options[selected_label]
    provider = st.selectbox("Provider", ["wan_local", "veo_cloud"], key="motion_provider")
    prompt = st.text_area(
        "Motion prompt",
        value=shot.visual_description or shot.image_prompt or "",
        key="motion_prompt",
    )
    config: dict[str, object] = {
        "fps": float(shot.episode.effective_fps),
        "max_generative_attempts": 3,
    }
    if provider == "wan_local":
        config.update(
            {
                "base_url": st.text_input(
                    "ComfyUI URL", "http://127.0.0.1:8188", key="motion_comfy_url"
                ),
                "workflow_path": st.text_input("Wan workflow JSON", key="motion_workflow"),
                "source_image_node_id": st.text_input(
                    "Source image node ID", key="motion_source_node"
                ),
                "prompt_node_id": st.text_input("Prompt node ID (optional)", key="motion_prompt_node"),
            }
        )
    else:
        config.update(
            {
                "model": st.text_input(
                    "Veo model", "veo-3.1-generate-preview", key="motion_veo_model"
                ),
                "cost_credit_type": "veo",
                "cost_is_estimated": True,
            }
        )
    if st.button("Queue motion", key="motion_enqueue"):
        try:
            with session_factory.begin() as session:
                job = enqueue_motion_job(
                    session,
                    shot_id=shot.id,
                    provider=provider,
                    config=config,
                    prompt=prompt,
                )
                job_id = job.id
            st.success(f"Queued motion Job #{job_id}")
        except (ValueError, OSError) as exc:
            st.error(str(exc))

    st.subheader("Jobs")
    with session_factory() as session:
        jobs = list(
            session.scalars(
                select(Job).where(
                    Job.episode_id == episode_id, Job.job_type == "motion_gen"
                ).order_by(Job.id.desc())
            )
        )
    if not jobs:
        st.caption("No motion jobs yet.")
    for job in jobs:
        columns = st.columns([1, 1, 3, 1])
        columns[0].write(f"Job #{job.id}")
        columns[1].write(job.status)
        columns[2].progress(int(job.progress_percent), text=job.error_message or job.provider or "")
        if job.status == "failed" and columns[3].button("Retry", key=f"motion_retry_{job.id}"):
            with session_factory.begin() as session:
                retry_motion_job(session, job.id)
            st.rerun()

    st.subheader("Motion variations")
    with session_factory() as session:
        assets = list(
            session.scalars(
                select(Asset).where(
                    Asset.shot_id == shot.id, Asset.asset_type == "video"
                ).order_by(Asset.version.desc())
            )
        )
        episode = shot.episode
    if not assets:
        st.caption("No motion variations for this shot.")
    for asset in assets:
        path = resolve(episode, asset.file_path)
        st.caption(f"v{asset.version} · {asset.provider or '-'} · {asset.duration_sec or 0:.2f}s")
        if path.is_file():
            st.video(str(path))
        else:
            st.error(f"Missing motion file: {path}")
        if st.button("Choose", key=f"motion_choose_{asset.id}", disabled=asset.is_chosen):
            with session_factory.begin() as session:
                choose_motion_asset(session, asset.id)
            st.rerun()
