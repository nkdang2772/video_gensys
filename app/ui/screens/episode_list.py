from __future__ import annotations

from pathlib import Path

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Episode, Series
from app.services.episode import create_episode
from app.services.errors import DomainError


def render(session_factory: sessionmaker[Session], library_root: Path) -> None:
    st.header("Episodes")
    with session_factory() as session:
        series_rows = list(
            session.scalars(select(Series).where(Series.deleted_at.is_(None)).order_by(Series.name))
        )
    if not series_rows:
        st.info("Create a Series first.")
        return
    series_options = {f"{series.name} ({series.slug})": series.id for series in series_rows}
    current_id = st.session_state.get("selected_series_id")
    default_index = next(
        (index for index, series_id in enumerate(series_options.values()) if series_id == current_id),
        0,
    )
    selected_label = st.selectbox(
        "Series", list(series_options), index=default_index, key="episode_series_select"
    )
    series_id = series_options[selected_label]
    st.session_state.selected_series_id = series_id

    with session_factory() as session:
        episodes = list(
            session.scalars(
                select(Episode).where(Episode.series_id == series_id).order_by(Episode.episode_number)
            )
        )
        table = [
            {
                "id": episode.id,
                "number": episode.episode_number,
                "slug": episode.slug,
                "title": episode.title,
                "status": episode.status,
                "root": episode.root_path,
            }
            for episode in episodes
        ]
    st.dataframe(table, use_container_width=True, hide_index=True)

    st.subheader("Create episode")
    number = st.number_input(
        "Episode number", min_value=1, step=1, value=len(episodes) + 1, key="episode_number"
    )
    title = st.text_input("Title", key="episode_title")
    slug = st.text_input("Slug (optional)", key="episode_slug")
    if st.button("Create episode", type="primary", key="episode_create_button"):
        try:
            with session_factory() as session:
                episode = create_episode(
                    session,
                    series_id=series_id,
                    episode_number=int(number),
                    title=title,
                    slug=slug or None,
                    library_root=library_root,
                )
                episode_id = episode.id
            st.session_state.selected_episode_id = episode_id
            st.success(f"Created episode #{episode_id}")
            st.rerun()
        except (DomainError, ValueError, OSError) as exc:
            st.error(str(exc))

    if episodes:
        options = {f"{episode.episode_number}: {episode.title}": episode.id for episode in episodes}
        selected = st.selectbox("Open episode", list(options), key="episode_open_select")
        if st.button("Open selected episode", key="episode_open_button"):
            st.session_state.selected_episode_id = options[selected]
            st.success(f"Opened {selected}")
