from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Asset, Episode, Reference, Scene, Shot
from app.paths import resolve
from app.services.errors import DomainError
from app.services.shot import bulk_update_shots, update_shot


def render(session_factory: sessionmaker[Session]) -> None:
    st.header("Shot Manager")
    episode_id = st.session_state.get("selected_episode_id")
    if episode_id is None:
        st.info("Open an Episode first.")
        return
    with session_factory() as session:
        episode = session.get(Episode, episode_id)
        if episode is None:
            st.error("Selected Episode no longer exists.")
            return
        scenes = list(
            session.scalars(select(Scene).where(Scene.episode_id == episode_id).order_by(Scene.order_index))
        )
        scene_options = {scene.title or str(scene.scene_number): scene.id for scene in scenes}
    scene_label = st.selectbox(
        "Filter scene", ["All", *scene_options], key="shot_filter_scene"
    )

    with session_factory() as session:
        statement = select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.order_index)
        if scene_label != "All":
            statement = statement.where(Shot.scene_id == scene_options[scene_label])
        shots = list(session.scalars(statement))
        rows = [
            {
                "id": shot.id,
                "shot_id": shot.shot_id,
                "order": shot.order_index,
                "speaker": shot.speaker or "",
                "visual_description": shot.visual_description or "",
                "characters": ", ".join(shot.characters_json or []),
                "motion_intent": shot.motion_intent,
                "status": shot.status,
                "duration": shot.audio_duration_sec,
            }
            for shot in shots
        ]
    if not rows:
        st.info("This Episode has no shots. Import a script first.")
        return
    edited = st.data_editor(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        disabled=["id", "shot_id", "order", "characters", "duration"],
        key="shot_editor",
    )
    if st.button("Save inline edits", key="shot_save_edits"):
        try:
            originals = {row["id"]: row for row in rows}
            with session_factory() as session:
                changed = 0
                for row in edited.to_dict("records"):
                    original = originals[row["id"]]
                    changes = {
                        field: row[field]
                        for field in ("speaker", "visual_description", "motion_intent", "status")
                        if row[field] != original[field]
                    }
                    if changes:
                        update_shot(session, int(row["id"]), **changes)
                        changed += 1
                session.commit()
            st.success(f"Updated {changed} shots")
        except (DomainError, ValueError) as exc:
            st.error(str(exc))

    st.subheader("Bulk assign characters")
    shot_options = {shot.shot_id: shot.id for shot in shots}
    selected_shot_labels = st.multiselect(
        "Shots", list(shot_options), key="shot_bulk_selection"
    )
    with session_factory() as session:
        episode = session.get(Episode, episode_id)
        character_refs = list(
            session.scalars(
                select(Reference).where(
                    Reference.reference_type == "character",
                    Reference.is_active.is_(True),
                    or_(
                        Reference.scope == "shared_across_series",
                        Reference.owning_series_id == episode.series_id,
                    ),
                ).order_by(Reference.name)
            )
        )
    character_options = {f"{reference.name} ({reference.slug})": reference.slug for reference in character_refs}
    selected_characters = st.multiselect(
        "Characters", list(character_options), key="shot_bulk_characters"
    )
    character_ids = [character_options[label] for label in selected_characters]
    primary_options = ["<none>", *character_ids]
    primary = st.selectbox("Primary character", primary_options, key="shot_bulk_primary")
    if st.button("Apply bulk characters", key="shot_bulk_apply"):
        try:
            with session_factory() as session:
                updated = bulk_update_shots(
                    session,
                    [shot_options[label] for label in selected_shot_labels],
                    characters_json=character_ids,
                    primary_character_id=None if primary == "<none>" else primary,
                )
                session.commit()
            st.success(f"Updated {len(updated)} shots")
        except (DomainError, ValueError) as exc:
            st.error(str(exc))

    st.subheader("Voice preview")
    if shots:
        preview_label = st.selectbox("Shot", list(shot_options), key="shot_audio_preview")
        with session_factory() as session:
            asset = session.scalar(
                select(Asset).where(
                    Asset.shot_id == shot_options[preview_label],
                    Asset.asset_type == "audio",
                    Asset.is_chosen.is_(True),
                )
            )
            episode = session.get(Episode, episode_id)
            audio_path = resolve(episode, asset.file_path) if asset and episode else None
        if audio_path and audio_path.is_file():
            st.audio(str(audio_path))
        else:
            st.caption("No chosen audio for this shot.")
