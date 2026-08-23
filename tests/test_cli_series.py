from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from app.db import create_db_engine


def test_cli_creates_series(tmp_path: Path) -> None:
    database = tmp_path / "cli.db"
    env = os.environ.copy()
    env["VIDEO_GENSYSTEM_DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env)
    result = subprocess.run(
        [sys.executable, "cli.py", "series", "create", "--name", "Tam Quốc"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert "slug=tam-quoc" in result.stdout
    engine = create_db_engine(env["VIDEO_GENSYSTEM_DATABASE_URL"])
    with engine.connect() as connection:
        assert connection.execute(text("SELECT name FROM series")).scalar_one() == "Tam Quốc"
    engine.dispose()
