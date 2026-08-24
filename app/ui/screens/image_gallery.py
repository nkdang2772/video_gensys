from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Asset, Episode, Job, Shot
from app.paths import resolve
from app.services.image_generation import (
    choose_image_asset,
    enqueue_character_batch,
    enqueue_image_job,
)


def _provider_config(provider: str, prefix: str) -> dict:
    if provider == "manual":
        return {"source_path": st.text_input("Manual PNG path", key=f"{prefix}_manual_path")}
    if provider == "comfyui":
        workflow_path = st.text_input("ComfyUI API workflow JSON", key=f"{prefix}_workflow")
        return {
            "workflow_path": workflow_path,
            "base_url": st.text_input(
                "ComfyUI URL", value="http://127.0.0.1:8188", key=f"{prefix}_comfy_url"
            ),
            "reference_image_nodes": st.text_area(
                "Reference node mappings (JSON list)", value="[]", key=f"{prefix}_ref_nodes"
            ),
        }
    st.caption("Google Flow requires the h2dev_flow side panel bridge and a token in the environment.")
    return {
        "bridge_port": st.number_input(
            "Flow bridge port", min_value=1, max_value=65535, value=8765, key=f"{prefix}_port"
        ),
        "downloads_root": st.text_input(
            "Chrome Downloads folder", value=str(Path.home() / "Downloads"), key=f"{prefix}_downloads"
        ),
        "cost_credit_amount": st.number_input(
            "Estimated Flow credits", min_value=0.0, value=0.0, key=f"{prefix}_cost"
        ),
        "cost_credit_type": "other",
        "cost_is_estimated": True,
    }


def render(session_factory: sessionmaker[Session], library_root: Path) -> None:
    del library_root
    st.header("Image Gallery")
    episode_id = st.session_state.get("selected_episode_id")
    if episode_id is None:
        st.info("Open an Episode first.")
        return
    with session_factory() as session:
        episode = session.get(Episode, episode_id)
        shots = list(
            session.scalars(
                select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.order_index)
            )
        )
    if episode is None:
        st.error("Selected Episode no longer exists.")
        return
    if not shots:
        st.info("This Episode has no shots. Import a script first.")
        return
    shot_options = {shot.shot_id: shot.id for shot in shots}
    selected_label = st.selectbox("Shot", list(shot_options), key="gallery_shot")
    shot_id = shot_options[selected_label]
    shot = next(item for item in shots if item.id == shot_id)

    with session_factory() as session:
        assets = list(
            session.scalars(
                select(Asset)
                .where(Asset.shot_id == shot_id, Asset.asset_type == "image")
                .order_by(Asset.version.desc())
            )
        )
    st.subheader("Variations")
    if not assets:
        st.caption("No image variations yet.")
    else:
        columns = st.columns(min(4, len(assets)))
        for index, asset in enumerate(assets):
            with columns[index % len(columns)]:
                path = resolve(episode, asset.file_path)
                if path.is_file():
                    st.image(str(path), caption=f"v{asset.version} · {asset.provider or '-'}")
                else:
                    st.error(f"Missing file for v{asset.version}")
                st.caption("Chosen" if asset.is_chosen else "Variation")
                if st.button("Choose", key=f"gallery_choose_{asset.id}", disabled=asset.is_chosen):
                    with session_factory.begin() as session:
                        choose_image_asset(session, asset.id)
                    st.rerun()

    st.subheader("Generate / regenerate")
    prompt = st.text_area(
        "Prompt",
        value=shot.image_prompt or shot.visual_description or "",
        key="gallery_prompt",
    )
    negative = st.text_area(
        "Negative prompt", value=shot.negative_prompt or "", key="gallery_negative"
    )
    provider = st.selectbox(
        "Provider", ["manual", "google_flow", "comfyui"], key="gallery_provider"
    )
    config = _provider_config(provider, "gallery_single")
    if st.button("Queue image variation", key="gallery_enqueue"):
        try:
            with session_factory.begin() as session:
                job = enqueue_image_job(
                    session,
                    shot_id=shot_id,
                    provider=provider,
                    config=config,
                    prompt=prompt,
                    negative_prompt=negative or None,
                )
                job_id = job.id
            st.success(f"Queued image Job #{job_id}")
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            st.error(str(exc))

    st.subheader("Character batch queue")
    st.caption("Pending shots are grouped by character batch key and pinned reference versions.")
    batch_provider = st.selectbox(
        "Batch provider", ["google_flow", "comfyui", "manual"], key="gallery_batch_provider"
    )
    batch_config = _provider_config(batch_provider, "gallery_batch")
    if st.button("Queue pending shots overnight", key="gallery_batch_enqueue"):
        try:
            if batch_provider == "manual":
                raise ValueError("Manual provider is only available for one shot at a time")
            with session_factory.begin() as session:
                jobs = enqueue_character_batch(
                    session,
                    episode_id=episode_id,
                    provider=batch_provider,
                    config=batch_config,
                )
            st.success(f"Queued {len(jobs)} image jobs")
        except (ValueError, OSError) as exc:
            st.error(str(exc))

    with session_factory() as session:
        active = list(
            session.scalars(
                select(Job).where(
                    Job.episode_id == episode_id,
                    Job.job_type == "image_gen",
                    Job.status.in_(("queued", "running", "failed")),
                ).order_by(Job.id.desc())
            )
        )
    st.dataframe(
        [
            {
                "job_id": job.id,
                "shot_id": job.shot_id,
                "status": job.status,
                "attempt": f"{job.attempt_count}/{job.max_attempts}",
                "error": job.error_message,
            }
            for job in active
        ],
        use_container_width=True,
        hide_index=True,
    )
