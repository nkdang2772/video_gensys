from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.episode import Episode
    from app.models.reference import Reference


class Series(TimestampMixin, Base):
    __tablename__ = "series"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    default_resolution: Mapped[str] = mapped_column(String(32), default="1920x1080", nullable=False)
    default_fps: Mapped[float] = mapped_column(default=30.0, nullable=False)
    default_aspect_ratio: Mapped[str] = mapped_column(String(32), default="16:9", nullable=False)
    style_anchor_reference_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "reference.id",
            name="fk_series_style_anchor_reference",
            ondelete="SET NULL",
            use_alter=True,
        )
    )
    palette_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    font_config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    episodes: Mapped[list["Episode"]] = relationship(back_populates="series", cascade="all, delete-orphan")
    references: Mapped[list["Reference"]] = relationship(
        back_populates="owning_series",
        cascade="all, delete-orphan",
        foreign_keys="Reference.owning_series_id",
    )
    style_anchor_reference: Mapped["Reference | None"] = relationship(
        foreign_keys=[style_anchor_reference_id], post_update=True
    )
