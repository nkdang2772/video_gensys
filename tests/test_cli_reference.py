from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def run_cli(arguments: list[str], env: dict[str, str]) -> str:
    result = subprocess.run(
        [sys.executable, "cli.py", *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    return result.stdout


def test_cli_creates_character_and_three_versions(tmp_path: Path) -> None:
    database = tmp_path / "cli.db"
    env = os.environ.copy()
    env["VIDEO_GENSYSTEM_DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env)
    run_cli(["series", "create", "--name", "Example Series"], env)
    with sqlite3.connect(database) as connection:
        series_id = connection.execute("SELECT id FROM series").fetchone()[0]
    output = run_cli(
        [
            "reference",
            "create",
            "--name",
            "Tao Thao",
            "--slug",
            "tao_thao",
            "--type",
            "character",
            "--series-id",
            str(series_id),
        ],
        env,
    )
    assert "slug=tao_thao" in output
    with sqlite3.connect(database) as connection:
        reference_id = connection.execute("SELECT id FROM reference").fetchone()[0]

    for number in range(1, 4):
        source = tmp_path / f"character_v{number}.png"
        source.write_bytes(f"version-{number}".encode())
        output = run_cli(
            [
                "reference",
                "add-version",
                "--reference-id",
                str(reference_id),
                "--file",
                str(source),
                "--library-root",
                str(tmp_path / "library"),
            ],
            env,
        )
        assert f"version={number}" in output

    listed = run_cli(
        ["reference", "list-versions", "--reference-id", str(reference_id)], env
    )
    assert listed.count("version=") == 3
