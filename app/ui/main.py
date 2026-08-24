from __future__ import annotations

import importlib

import streamlit as st

from app.ui.context import get_library_root, get_session_factory

PAGES = {
    "Series": "app.ui.screens.series_list",
    "Episodes": "app.ui.screens.episode_list",
    "Import": "app.ui.screens.import",
    "Shot Manager": "app.ui.screens.shot_manager",
    "References": "app.ui.screens.reference",
    "Image Gallery": "app.ui.screens.image_gallery",
}


def main() -> None:
    st.set_page_config(page_title="Video GenSystem", layout="wide")
    st.title("Video GenSystem")
    st.sidebar.caption("Local production workspace")
    page = st.sidebar.radio("Screen", list(PAGES), key="main_navigation")
    selected_series = st.session_state.get("selected_series_id")
    selected_episode = st.session_state.get("selected_episode_id")
    st.sidebar.caption(f"Series ID: {selected_series or '-'}")
    st.sidebar.caption(f"Episode ID: {selected_episode or '-'}")

    module = importlib.import_module(PAGES[page])
    session_factory = get_session_factory()
    library_root = get_library_root()
    if page in {"Episodes", "References", "Image Gallery"}:
        module.render(session_factory, library_root)
    else:
        module.render(session_factory)
