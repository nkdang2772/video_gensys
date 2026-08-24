from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import utc_now

if TYPE_CHECKING:
    from app.models.episode import Episode
    from app.models.qa import SimpleQaNote
    from app.models.shot import Shot


class Asset(Base):
    __tablename__ = "asset"
    __table_args__ = (
        UniqueConstraint("episode_id", "shot_id", "asset_type", "version", name="uq_asset_version"),
        Index(
            "uq_asset_one_chosen_per_shot_type",
            "shot_id",
            "asset_type",
            unique=True,
            sqlite_where=text("is_chosen = 1 AND shot_id IS NOT NULL"),
        ),
        CheckConstraint(
            "asset_type IN ('audio','image','video','proxy','subtitle','music','sfx')",
            name="ck_asset_type",
        ),
        CheckConstraint("version > 0", name="ck_asset_version_positive"),
        CheckConstraint(
            "duration_sec IS NULL OR duration_sec >= 0",
            name="ck_asset_duration",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episode.id", ondelete="CASCADE"), nullable=False)
    shot_id: Mapped[int | None] = mapped_column(ForeignKey("shot.id", ondelete="CASCADE"))
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    is_chosen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(255))
    prompt: Mapped[str | None] = mapped_column(Text)
    negative_prompt: Mapped[str | None] = mapped_column(Text)
    seed: Mapped[int | None]
    workflow_id: Mapped[str | None] = mapped_column(String(255))
    source_path: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    proxy_path: Mapped[str | None] = mapped_column(Text)
    width: Mapped[int | None]
    height: Mapped[int | None]
    duration_sec: Mapped[float | None]
    frame_rate: Mapped[float | None]
    codec: Mapped[str | None] = mapped_column(String(64))
    file_size: Mapped[int | None]
    checksum: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)

    episode: Mapped["Episode"] = relationship(back_populates="assets")
    shot: Mapped["Shot | None"] = relationship(back_populates="assets")
    qa_notes: Mapped[list["SimpleQaNote"]] = relationship(back_populates="asset")
