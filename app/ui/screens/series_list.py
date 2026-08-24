from __future__ import annotations

import streamlit as st
from sqlalchemy.orm import Session, sessionmaker

from app.services.errors import DomainError
from app.services.series import create_series, list_series


def render(session_factory: sessionmaker[Session]) -> None:
    st.header("Series")
    with session_factory() as session:
        series_rows = list_series(session)
        table = [
            {
                "id": series.id,
                "slug": series.slug,
                "name": series.name,
                "resolution": series.default_resolution,
                "fps": series.default_fps,
                "aspect_ratio": series.default_aspect_ratio,
            }
            for series in series_rows
        ]
    st.dataframe(table, use_container_width=True, hide_index=True)

    st.subheader("Create series")
    name = st.text_input("Name", key="series_create_name")
    slug = st.text_input("Slug (optional)", key="series_create_slug")
    col1, col2, col3 = st.columns(3)
    resolution = col1.text_input("Resolution", value="1920x1080", key="series_resolution")
    fps = col2.number_input("FPS", min_value=1.0, value=30.0, key="series_fps")
    aspect_ratio = col3.text_input("Aspect ratio", value="16:9", key="series_aspect")
    if st.button("Create series", type="primary", key="series_create_button"):
        try:
            with session_factory.begin() as session:
                series = create_series(
                    session,
                    name=name,
                    slug=slug or None,
                    default_resolution=resolution,
                    default_fps=float(fps),
                    default_aspect_ratio=aspect_ratio,
                )
                series_id = series.id
            st.session_state.selected_series_id = series_id
            st.success(f"Created series #{series_id}")
            st.rerun()
        except (DomainError, ValueError) as exc:
            st.error(str(exc))

    if series_rows:
        options = {f"{series.name} ({series.slug})": series.id for series in series_rows}
        labels = list(options)
        selected = st.selectbox("Open series", labels, key="series_open_select")
        if st.button("Open selected series", key="series_open_button"):
            st.session_state.selected_series_id = options[selected]
            st.success(f"Opened {selected}")
