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

EXPECTED_COLUMNS = {
    "series": {
        "id", "slug", "name", "description", "default_resolution", "default_fps",
        "default_aspect_ratio", "style_anchor_reference_id", "palette_json",
        "font_config_json", "created_at", "updated_at", "deleted_at",
    },
    "episode": {
        "id", "series_id", "episode_number", "slug", "title", "status",
        "effective_resolution", "effective_fps", "effective_aspect_ratio",
        "style_anchor_version_snapshot", "palette_snapshot_json",
        "font_config_snapshot_json", "target_duration_sec", "root_path",
        "created_at", "updated_at",
    },
    "scene": {"id", "episode_id", "scene_number", "title", "description", "order_index"},
    "shot": {
        "id", "episode_id", "scene_id", "shot_id", "order_index", "speaker",
        "voice_text", "subtitle_text", "visual_description", "image_prompt",
        "negative_prompt", "characters_json", "primary_character_id",
        "location_reference_id", "character_batch_key", "audio_start_sec",
        "audio_end_sec", "audio_duration_sec", "head_padding_sec", "tail_padding_sec",
        "planned_duration_sec",
        "motion_intent", "motion_provider", "hero_flag", "camera_motion_json",
        "motion_fill_policy", "status", "notes",
    },
    "reference": {
        "id", "slug", "name", "reference_type", "scope", "owning_series_id",
        "current_version", "created_at", "updated_at", "is_active",
        "generation_prompt", "aliases_json",
    },
    "reference_version": {
        "id", "reference_id", "version", "file_path", "descriptor_json", "checksum",
        "created_at",
    },
    "episode_reference_pin": {"id", "episode_id", "reference_id", "reference_version_id"},
    "asset": {
        "id", "episode_id", "shot_id", "asset_type", "version", "is_chosen",
        "provider", "model", "prompt", "negative_prompt", "seed", "workflow_id",
        "source_path", "file_path", "proxy_path", "width", "height", "duration_sec",
        "frame_rate", "codec", "file_size", "checksum", "created_at",
    },
    "job": {
        "id", "episode_id", "shot_id", "job_type", "provider", "priority", "status",
        "progress_percent", "attempt_count", "max_attempts", "input_payload_json",
        "output_payload_json", "error_message", "worker_pid", "cost_usd",
        "cost_credit_amount", "cost_credit_type", "cost_is_estimated", "created_at",
        "started_at", "completed_at",
    },
    "simple_qa_note": {
        "id", "episode_id", "shot_id", "asset_id", "category", "note", "is_resolved",
        "created_at",
    },
}


def _migrate_database(tmp_path: Path) -> sqlite3.Connection:
    database = tmp_path / "migration.db"
    env = os.environ.copy()
    env["VIDEO_GENSYSTEM_DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env)

    connection = sqlite3.connect(database)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _insert_one_record_per_table(connection: sqlite3.Connection) -> None:
    now = "2026-08-24T00:00:00+00:00"
    connection.execute(
        "INSERT INTO series (id,slug,name,created_at,updated_at) VALUES (1,'demo-series','Demo Series',?,?)",
        (now, now),
    )
    connection.execute(
        "INSERT INTO episode (id,series_id,episode_number,slug,title,effective_resolution,effective_fps,effective_aspect_ratio,root_path,created_at,updated_at) "
        "VALUES (1,1,1,'episode-one','Episode One','1920x1080',30,'16:9','episodes/episode-one',?,?)",
        (now, now),
    )
    connection.execute("INSERT INTO scene (id,episode_id,scene_number,order_index) VALUES (1,1,1,1)")
    connection.execute(
        "INSERT INTO reference (id,slug,name,reference_type,scope,owning_series_id,created_at,updated_at) "
        "VALUES (1,'hero','Hero','character','series_specific',1,?,?)",
        (now, now),
    )
    connection.execute(
        "INSERT INTO reference_version (id,reference_id,version,file_path,checksum,created_at) VALUES (1,1,1,'ref.png','abc',?)",
        (now,),
    )
    connection.execute(
        "INSERT INTO shot (id,episode_id,scene_id,shot_id,order_index,characters_json) VALUES (1,1,1,'s001',1,'[\"hero\"]')"
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
        "INSERT INTO job (id,episode_id,shot_id,job_type,created_at) VALUES (1,1,1,'image_gen',?)",
        (now,),
    )
    connection.execute(
        "INSERT INTO simple_qa_note (id,episode_id,shot_id,asset_id,category,note,created_at) "
        "VALUES (1,1,1,1,'content','check',?)",
        (now,),
    )
    connection.commit()


def test_migration_creates_complete_schema_and_accepts_raw_records(tmp_path: Path) -> None:
    connection = _migrate_database(tmp_path)
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        if row[0] not in {"alembic_version", "sqlite_sequence"}
    }
    assert tables == EXPECTED_TABLES

    actual_columns = {
        table: {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
        for table in EXPECTED_TABLES
    }
    assert actual_columns == EXPECTED_COLUMNS

    _insert_one_record_per_table(connection)
    for table in EXPECTED_TABLES:
        assert connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == 1
    connection.close()


def test_migration_enforces_foreign_key_check_and_partial_unique_constraints(tmp_path: Path) -> None:
    connection = _migrate_database(tmp_path)
    _insert_one_record_per_table(connection)
    now = "2026-08-24T00:00:00+00:00"
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO asset (episode_id,shot_id,asset_type,version,is_chosen,file_path,created_at) "
            "VALUES (1,1,'image',2,1,'images/s001_v2.png',?)",
            (now,),
        )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO reference_version (reference_id,version,file_path,checksum,created_at) "
            "VALUES (1,0,'invalid.png','bad',?)",
            (now,),
        )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO simple_qa_note (episode_id,category,note,created_at) "
            "VALUES (999,'content','orphan',?)",
            (now,),
        )
    connection.close()
