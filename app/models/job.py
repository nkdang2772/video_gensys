from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.mixins import utc_now

if TYPE_CHECKING:
    from app.models.episode import Episode
    from app.models.shot import Shot


class Job(Base):
    __tablename__ = "job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','done','failed','cancelled')",
            name="ck_job_status",
        ),
        CheckConstraint(
            "priority IN ('high','normal','image','gpu','overnight','export')",
            name="ck_job_priority",
        ),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100",
            name="ck_job_progress",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0",
            name="ck_job_attempts",
        ),
        CheckConstraint(
            "cost_credit_type IS NULL OR cost_credit_type IN ('veo','imagen','other')",
            name="ck_job_credit_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episode.id", ondelete="CASCADE"), nullable=False)
    shot_id: Mapped[int | None] = mapped_column(ForeignKey("shot.id", ondelete="CASCADE"))
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64))
    priority: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    progress_percent: Mapped[float] = mapped_column(default=0.0, nullable=False)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=3, nullable=False)
    input_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    output_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    worker_pid: Mapped[int | None]
    cost_usd: Mapped[float | None]
    cost_credit_amount: Mapped[float | None]
    cost_credit_type: Mapped[str | None] = mapped_column(String(32))
    cost_is_estimated: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]

    episode: Mapped["Episode"] = relationship(back_populates="jobs")
    shot: Mapped["Shot | None"] = relationship(back_populates="jobs")
