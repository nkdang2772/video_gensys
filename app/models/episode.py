from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.asset import Asset
    from app.models.job import Job
    from app.models.qa import SimpleQaNote
    from app.models.reference import Reference, ReferenceVersion
    from app.models.scene import Scene
    from app.models.series import Series
    from app.models.shot import Shot


class Episode(TimestampMixin, Base):
    __tablename__ = "episode"
    __table_args__ = (UniqueConstraint("series_id", "episode_number", name="uq_episode_series_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), nullable=False)
    episode_number: Mapped[int] = mapped_column(nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    effective_resolution: Mapped[str] = mapped_column(String(32), nullable=False)
    effective_fps: Mapped[float] = mapped_column(nullable=False)
    effective_aspect_ratio: Mapped[str] = mapped_column(String(32), nullable=False)
    style_anchor_version_snapshot: Mapped[int | None]
    palette_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    font_config_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    target_duration_sec: Mapped[float | None]
    root_path: Mapped[str] = mapped_column(Text, nullable=False)

    series: Mapped["Series"] = relationship(back_populates="episodes")
    scenes: Mapped[list["Scene"]] = relationship(back_populates="episode", cascade="all, delete-orphan")
    shots: Mapped[list["Shot"]] = relationship(back_populates="episode", cascade="all, delete-orphan")
    reference_pins: Mapped[list["EpisodeReferencePin"]] = relationship(
        back_populates="episode", cascade="all, delete-orphan"
    )
    assets: Mapped[list["Asset"]] = relationship(back_populates="episode", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="episode", cascade="all, delete-orphan")
    qa_notes: Mapped[list["SimpleQaNote"]] = relationship(back_populates="episode", cascade="all, delete-orphan")


class EpisodeReferencePin(Base):
    __tablename__ = "episode_reference_pin"
    __table_args__ = (UniqueConstraint("episode_id", "reference_id", name="uq_episode_reference_pin"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episode.id", ondelete="CASCADE"), nullable=False)
    reference_id: Mapped[int] = mapped_column(ForeignKey("reference.id", ondelete="RESTRICT"), nullable=False)
    reference_version_id: Mapped[int] = mapped_column(
        ForeignKey("reference_version.id", ondelete="RESTRICT"), nullable=False
    )

    episode: Mapped["Episode"] = relationship(back_populates="reference_pins")
    reference: Mapped["Reference"] = relationship(back_populates="episode_pins")
    reference_version: Mapped["ReferenceVersion"] = relationship(back_populates="episode_pins")

