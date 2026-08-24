from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, utc_now

if TYPE_CHECKING:
    from app.models.episode import EpisodeReferencePin
    from app.models.series import Series


class Reference(TimestampMixin, Base):
    __tablename__ = "reference"
    __table_args__ = (
        CheckConstraint(
            "reference_type IN ('character','style','location','prop','map')",
            name="ck_reference_type",
        ),
        CheckConstraint(
            "scope IN ('series_specific','shared_across_series')",
            name="ck_reference_scope",
        ),
        CheckConstraint(
            "(scope = 'series_specific' AND owning_series_id IS NOT NULL) OR "
            "(scope = 'shared_across_series' AND owning_series_id IS NULL)",
            name="ck_reference_scope_owner",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), default="series_specific", nullable=False)
    owning_series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    current_version: Mapped[int] = mapped_column(default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    owning_series: Mapped["Series | None"] = relationship(
        back_populates="references", foreign_keys=[owning_series_id]
    )
    versions: Mapped[list["ReferenceVersion"]] = relationship(
        back_populates="reference", cascade="all, delete-orphan"
    )
    episode_pins: Mapped[list["EpisodeReferencePin"]] = relationship(back_populates="reference")


class ReferenceVersion(Base):
    __tablename__ = "reference_version"
    __table_args__ = (
        UniqueConstraint("reference_id", "version", name="uq_reference_version"),
        CheckConstraint("version > 0", name="ck_reference_version_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[int] = mapped_column(ForeignKey("reference.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    descriptor_json: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    reference: Mapped["Reference"] = relationship(back_populates="versions")
    episode_pins: Mapped[list["EpisodeReferencePin"]] = relationship(back_populates="reference_version")
