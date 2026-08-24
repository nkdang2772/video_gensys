from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from sqlalchemy.orm import Session, sessionmaker

from app.db import DATABASE_URL_ENV, DEFAULT_DATABASE_URL, create_db_engine, create_session_factory

LIBRARY_ROOT_ENV = "VIDEO_GENSYSTEM_LIBRARY_ROOT"


@st.cache_resource(show_spinner=False)
def session_factory_for_url(database_url: str) -> sessionmaker[Session]:
    return create_session_factory(create_db_engine(database_url))


def get_session_factory() -> sessionmaker[Session]:
    return session_factory_for_url(os.getenv(DATABASE_URL_ENV, DEFAULT_DATABASE_URL))


def get_library_root() -> Path:
    configured = os.getenv(LIBRARY_ROOT_ENV, "library")
    return Path(configured).expanduser().resolve()
