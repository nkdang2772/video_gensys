import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_every_connection_has_sqlite_pragmas(engine) -> None:
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar_one().lower() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() == 5000
        assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1


def test_alembic_rejects_unknown_revision(tmp_path) -> None:
    env = os.environ.copy()
    env["VIDEO_GENSYSTEM_DATABASE_URL"] = f"sqlite:///{(tmp_path / 'invalid.db').as_posix()}"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "not-a-real-revision"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Can't locate revision identified by 'not-a-real-revision'" in result.stderr
