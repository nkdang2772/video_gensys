from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

EXPECTED_TABLES = {
    "series",
    "episode",
    "scene",
    "shot",
    "reference",
    "reference_version",
    "episode_reference_pin",
    "asset",
    "job",
    "simple_qa_note",
}


def test_migration_and_raw_sql_constraints(tmp_path: Path) -> None:
    database = tmp_path / "migration.db"
    env = os.environ.copy()
    env["VIDEO_GENSYSTEM_DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env)

    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys=ON")
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        if row[0] not in {"alembic_version", "sqlite_sequence"}
    }
    assert tables == EXPECTED_TABLES

    now = "2026-08-24T00:00:00+00:00"
    connection.execute(
        "INSERT INTO series (id,slug,name,created_at,updated_at) VALUES (1,'tam-quoc','Tam Quoc',?,?)",
        (now, now),
    )
    connection.execute(
        "INSERT INTO episode (id,series_id,episode_number,slug,title,effective_resolution,effective_fps,effective_aspect_ratio,root_path,created_at,updated_at) "
        "VALUES (1,1,1,'xich-bich','Xich Bich','1920x1080',30,'16:9','episodes/xich-bich',?,?)",
        (now, now),
    )
    connection.execute("INSERT INTO scene (id,episode_id,scene_number,order_index) VALUES (1,1,1,1)")
    connection.execute(
        "INSERT INTO reference (id,slug,name,reference_type,scope,owning_series_id,created_at,updated_at) "
        "VALUES (1,'tao-thao','Tao Thao','character','series_specific',1,?,?)",
        (now, now),
    )
    connection.execute(
        "INSERT INTO reference_version (id,reference_id,version,file_path,checksum,created_at) VALUES (1,1,1,'ref.png','abc',?)",
        (now,),
    )
    connection.execute(
        "INSERT INTO shot (id,episode_id,scene_id,shot_id,order_index,characters_json) VALUES (1,1,1,'s001',1,'[\"tao_thao\"]')"
    )
    connection.execute(
        "INSERT INTO episode_reference_pin (id,episode_id,reference_id,reference_version_id) VALUES (1,1,1,1)"
    )
    connection.execute(
        "INSERT INTO asset (id,episode_id,shot_id,asset_type,version,is_chosen,file_path,created_at) "
        "VALUES (1,1,1,'image',1,1,'images/s001.png',?)",
        (now,),
    )
    connection.execute(
        "INSERT INTO job (id,episode_id,shot_id,job_type,created_at) VALUES (1,1,1,'image_generate',?)",
        (now,),
    )
    connection.execute(
        "INSERT INTO simple_qa_note (id,episode_id,shot_id,asset_id,category,note,created_at) "
        "VALUES (1,1,1,1,'content','check',?)",
        (now,),
    )
    connection.commit()

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO asset (episode_id,shot_id,asset_type,version,is_chosen,file_path,created_at) "
            "VALUES (1,1,'image',2,1,'images/s001_v2.png',?)",
            (now,),
        )
    connection.close()

