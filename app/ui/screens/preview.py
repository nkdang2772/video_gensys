from __future__ import annotations

from pathlib import Path

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.media.concat import render_sequence_preview, render_shot_preview
from app.models import Episode, Scene, Shot


def render(session_factory: sessionmaker[Session], library_root: Path) -> None:
    del library_root
    st.header("Preview")
    episode_id = st.session_state.get("selected_episode_id")
    if episode_id is None:
        st.info("Open an Episode first.")
        return
    with session_factory() as session:
        episode = session.get(Episode, episode_id)
        shots = list(session.scalars(select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.order_index)))
        scenes = list(session.scalars(select(Scene).where(Scene.episode_id == episode_id).order_by(Scene.order_index)))
    if episode is None or not shots:
        st.info("This Episode has no shots. Import a script first.")
        return
    mode = st.radio("Preview scope", ["Shot", "Scene", "Full"], horizontal=True)
    force = st.checkbox("Rebuild proxy", value=False)
    selected_shot = None
    selected_scene = None
    if mode == "Shot":
        selected_shot = st.selectbox("Shot", shots, format_func=lambda item: item.shot_id)
    elif mode == "Scene":
        selected_scene = st.selectbox("Scene", scenes, format_func=lambda item: f"Scene {item.scene_number}: {item.title or ''}") if scenes else None
        if selected_scene is None:
            st.warning("No Scene is available.")
            return
    if st.button("Build preview", type="primary"):
        try:
            with session_factory() as session:
                current_episode = session.get(Episode, episode_id)
                if mode == "Shot":
                    current_shot = session.get(Shot, selected_shot.id)
                    result = render_shot_preview(current_episode, current_shot, force=force)
                else:
                    result = render_sequence_preview(
                        session,
                        episode_id,
                        scene_id=selected_scene.id if selected_scene is not None else None,
                        force=force,
                    )
            st.session_state["preview_output"] = str(result.output_path)
            st.session_state["preview_placeholders"] = list(result.placeholder_shot_ids)
            st.success(f"Built {result.shot_count} shot(s), {result.duration_sec:.2f}s")
        except (ValueError, OSError, RuntimeError) as exc:
            st.error(str(exc))
    output = st.session_state.get("preview_output")
    if output and Path(output).is_file():
        st.video(output, loop=mode == "Shot")
        st.caption(output)
        placeholders = st.session_state.get("preview_placeholders") or []
        if placeholders:
            st.warning("Red placeholders: " + ", ".join(placeholders))
