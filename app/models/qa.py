from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import utc_now

if TYPE_CHECKING:
    from app.models.asset import Asset
    from app.models.episode import Episode
    from app.models.shot import Shot


class SimpleQaNote(Base):
    __tablename__ = "simple_qa_note"

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episode.id", ondelete="CASCADE"), nullable=False)
    shot_id: Mapped[int | None] = mapped_column(ForeignKey("shot.id", ondelete="CASCADE"))
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("asset.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)

    episode: Mapped["Episode"] = relationship(back_populates="qa_notes")
    shot: Mapped["Shot | None"] = relationship(back_populates="qa_notes")
    asset: Mapped["Asset | None"] = relationship(back_populates="qa_notes")

