from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin, utc_now

if TYPE_CHECKING:
    from app.models.episode import EpisodeReferencePin
    from app.models.series import Series


class Reference(TimestampMixin, Base):
    __tablename__ = "reference"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), default="series_specific", nullable=False)
    owning_series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    current_version: Mapped[int] = mapped_column(default=0, nullable=False)

    owning_series: Mapped["Series | None"] = relationship(
        back_populates="references", foreign_keys=[owning_series_id]
    )
    versions: Mapped[list["ReferenceVersion"]] = relationship(
        back_populates="reference", cascade="all, delete-orphan"
    )
    episode_pins: Mapped[list["EpisodeReferencePin"]] = relationship(back_populates="reference")


class ReferenceVersion(Base):
    __tablename__ = "reference_version"
    __table_args__ = (UniqueConstraint("reference_id", "version", name="uq_reference_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[int] = mapped_column(ForeignKey("reference.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    descriptor_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    reference: Mapped["Reference"] = relationship(back_populates="versions")
    episode_pins: Mapped[list["EpisodeReferencePin"]] = relationship(back_populates="reference_version")
