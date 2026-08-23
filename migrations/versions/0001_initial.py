"""Initial ten-table schema.

Revision ID: 0001
Revises:
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "series",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("default_resolution", sa.String(32), nullable=False, server_default="1920x1080"),
        sa.Column("default_fps", sa.Float(), nullable=False, server_default="30"),
        sa.Column("default_aspect_ratio", sa.String(32), nullable=False, server_default="16:9"),
        sa.Column(
            "style_anchor_reference_id",
            sa.Integer(),
            sa.ForeignKey("reference.id", name="fk_series_style_anchor_reference", ondelete="SET NULL"),
        ),
        sa.Column("palette_json", sa.JSON()),
        sa.Column("font_config_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "episode",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_id", sa.Integer(), sa.ForeignKey("series.id", ondelete="CASCADE"), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("effective_resolution", sa.String(32), nullable=False),
        sa.Column("effective_fps", sa.Float(), nullable=False),
        sa.Column("effective_aspect_ratio", sa.String(32), nullable=False),
        sa.Column("style_anchor_version_snapshot", sa.Integer()),
        sa.Column("palette_snapshot_json", sa.JSON()),
        sa.Column("font_config_snapshot_json", sa.JSON()),
        sa.Column("target_duration_sec", sa.Float()),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("series_id", "episode_number", name="uq_episode_series_number"),
    )
    op.create_table(
        "scene",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("episode.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.UniqueConstraint("episode_id", "scene_number", name="uq_scene_episode_number"),
    )
    op.create_table(
        "reference",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("reference_type", sa.String(32), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False, server_default="series_specific"),
        sa.Column("owning_series_id", sa.Integer(), sa.ForeignKey("series.id", ondelete="CASCADE")),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("reference_type IN ('character','style','location','prop','map')", name="ck_reference_type"),
        sa.CheckConstraint("scope IN ('series_specific','shared_across_series')", name="ck_reference_scope"),
        sa.CheckConstraint(
            "(scope = 'series_specific' AND owning_series_id IS NOT NULL) OR "
            "(scope = 'shared_across_series' AND owning_series_id IS NULL)",
            name="ck_reference_scope_owner",
        ),
    )
    op.create_table(
        "reference_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reference_id", sa.Integer(), sa.ForeignKey("reference.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("descriptor_json", sa.JSON()),
        sa.Column("checksum", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("reference_id", "version", name="uq_reference_version"),
        sa.CheckConstraint("version > 0", name="ck_reference_version_positive"),
    )
    op.create_table(
        "shot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("episode.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scene.id", ondelete="SET NULL")),
        sa.Column("shot_id", sa.String(100), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(255)),
        sa.Column("voice_text", sa.Text()),
        sa.Column("subtitle_text", sa.Text()),
        sa.Column("visual_description", sa.Text()),
        sa.Column("image_prompt", sa.Text()),
        sa.Column("negative_prompt", sa.Text()),
        sa.Column("characters_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("primary_character_id", sa.String(255)),
        sa.Column("location_reference_id", sa.Integer(), sa.ForeignKey("reference.id", ondelete="SET NULL")),
        sa.Column("character_batch_key", sa.String(64)),
        sa.Column("audio_start_sec", sa.Float()),
        sa.Column("audio_end_sec", sa.Float()),
        sa.Column("audio_duration_sec", sa.Float()),
        sa.Column("head_padding_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tail_padding_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("motion_intent", sa.String(32), nullable=False, server_default="static"),
        sa.Column("motion_provider", sa.String(32), nullable=False, server_default="none"),
        sa.Column("hero_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("camera_motion_json", sa.JSON()),
        sa.Column("motion_fill_policy", sa.String(16), nullable=False, server_default="extend"),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("episode_id", "shot_id", name="uq_shot_episode_shot_id"),
        sa.CheckConstraint("audio_duration_sec IS NULL OR audio_duration_sec >= 0", name="ck_shot_audio_duration"),
        sa.CheckConstraint("head_padding_sec >= 0 AND tail_padding_sec >= 0", name="ck_shot_padding"),
        sa.CheckConstraint("motion_intent IN ('static','pan','parallax','sprite','map','generative')", name="ck_shot_motion_intent"),
        sa.CheckConstraint("motion_provider IN ('none','internal_kenburns','fusion_parallax','sprite_local','map_local','wan_local','veo_cloud')", name="ck_shot_motion_provider"),
        sa.CheckConstraint("motion_fill_policy IN ('extend','loop','split')", name="ck_shot_fill_policy"),
    )
    op.create_table(
        "episode_reference_pin",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("episode.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reference_id", sa.Integer(), sa.ForeignKey("reference.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reference_version_id", sa.Integer(), sa.ForeignKey("reference_version.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("episode_id", "reference_id", name="uq_episode_reference_pin"),
    )
    op.create_table(
        "asset",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("episode.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shot_id", sa.Integer(), sa.ForeignKey("shot.id", ondelete="CASCADE")),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_chosen", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider", sa.String(64)),
        sa.Column("model", sa.String(255)),
        sa.Column("prompt", sa.Text()),
        sa.Column("negative_prompt", sa.Text()),
        sa.Column("seed", sa.Integer()),
        sa.Column("workflow_id", sa.String(255)),
        sa.Column("source_path", sa.Text()),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("proxy_path", sa.Text()),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("duration_sec", sa.Float()),
        sa.Column("frame_rate", sa.Float()),
        sa.Column("codec", sa.String(64)),
        sa.Column("file_size", sa.Integer()),
        sa.Column("checksum", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("episode_id", "shot_id", "asset_type", "version", name="uq_asset_version"),
        sa.CheckConstraint("asset_type IN ('audio','image','video','proxy','subtitle','music','sfx')", name="ck_asset_type"),
        sa.CheckConstraint("version > 0", name="ck_asset_version_positive"),
        sa.CheckConstraint("duration_sec IS NULL OR duration_sec >= 0", name="ck_asset_duration"),
    )
    op.create_index(
        "uq_asset_one_chosen_per_shot_type",
        "asset",
        ["shot_id", "asset_type"],
        unique=True,
        sqlite_where=sa.text("is_chosen = 1 AND shot_id IS NOT NULL"),
    )
    op.create_table(
        "job",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("episode.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shot_id", sa.Integer(), sa.ForeignKey("shot.id", ondelete="CASCADE")),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64)),
        sa.Column("priority", sa.String(32), nullable=False, server_default="normal"),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("progress_percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("input_payload_json", sa.JSON()),
        sa.Column("output_payload_json", sa.JSON()),
        sa.Column("error_message", sa.Text()),
        sa.Column("worker_pid", sa.Integer()),
        sa.Column("cost_usd", sa.Float()),
        sa.Column("cost_credit_amount", sa.Float()),
        sa.Column("cost_credit_type", sa.String(32)),
        sa.Column("cost_is_estimated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('queued','running','done','failed','cancelled')", name="ck_job_status"),
        sa.CheckConstraint("priority IN ('high','normal','image','gpu','overnight','export')", name="ck_job_priority"),
        sa.CheckConstraint("progress_percent >= 0 AND progress_percent <= 100", name="ck_job_progress"),
        sa.CheckConstraint("attempt_count >= 0 AND max_attempts > 0", name="ck_job_attempts"),
        sa.CheckConstraint("cost_credit_type IS NULL OR cost_credit_type IN ('veo','imagen','other')", name="ck_job_credit_type"),
    )
    op.create_table(
        "simple_qa_note",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("episode_id", sa.Integer(), sa.ForeignKey("episode.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shot_id", sa.Integer(), sa.ForeignKey("shot.id", ondelete="CASCADE")),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("asset.id", ondelete="CASCADE")),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("simple_qa_note")
    op.drop_table("job")
    op.drop_index("uq_asset_one_chosen_per_shot_type", table_name="asset")
    op.drop_table("asset")
    op.drop_table("episode_reference_pin")
    op.drop_table("shot")
    op.drop_table("reference_version")
    op.drop_table("reference")
    op.drop_table("scene")
    op.drop_table("episode")
    op.drop_table("series")
