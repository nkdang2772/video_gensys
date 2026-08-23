from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.episode import Episode
    from app.models.shot import Shot


class Scene(Base):
    __tablename__ = "scene"
    __table_args__ = (UniqueConstraint("episode_id", "scene_number", name="uq_scene_episode_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episode.id", ondelete="CASCADE"), nullable=False)
    scene_number: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(nullable=False)

    episode: Mapped["Episode"] = relationship(back_populates="scenes")
    shots: Mapped[list["Shot"]] = relationship(back_populates="scene")

