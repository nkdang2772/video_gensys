from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

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


@pytest.fixture(scope="session")
def ffprobe_executable() -> str:
    candidates: list[Path] = []
    discovered = shutil.which("ffprobe")
    if discovered:
        candidates.append(Path(discovered))
    conda_envs = Path.home() / "anaconda3" / "envs"
    if conda_envs.is_dir():
        candidates.extend(conda_envs.glob("*/Library/bin/ffprobe.exe"))
    package_root = Path.home() / "anaconda3" / "pkgs"
    if package_root.is_dir():
        candidates.extend(package_root.glob("ffmpeg-*/Library/bin/ffprobe.exe"))

    for candidate in candidates:
        try:
            result = subprocess.run(
                [str(candidate), "-version"],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return str(candidate)
    pytest.skip("No working ffprobe executable is installed")
