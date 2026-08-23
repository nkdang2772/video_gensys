from __future__ import annotations

import pytest

from app.db import Base, create_db_engine, create_session_factory
import app.models  # noqa: F401


@pytest.fixture
def engine(tmp_path):
    db_engine = create_db_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(db_engine)
    try:
        yield db_engine
    finally:
        db_engine.dispose()


@pytest.fixture
def session(engine):
    factory = create_session_factory(engine)
    with factory() as db_session:
        yield db_session

