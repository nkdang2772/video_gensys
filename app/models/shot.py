from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, ForeignKey, JSON, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, validates

from app.db import Base

if TYPE_CHECKING:
    from app.models.asset import Asset
    from app.models.episode import Episode
    from app.models.job import Job
    from app.models.qa import SimpleQaNote
    from app.models.reference import Reference
    from app.models.scene import Scene


class Shot(Base):
    __tablename__ = "shot"
    __table_args__ = (UniqueConstraint("episode_id", "shot_id", name="uq_shot_episode_shot_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(ForeignKey("episode.id", ondelete="CASCADE"), nullable=False)
    scene_id: Mapped[int | None] = mapped_column(ForeignKey("scene.id", ondelete="SET NULL"))
    shot_id: Mapped[str] = mapped_column(String(100), nullable=False)
    order_index: Mapped[int] = mapped_column(nullable=False)
    speaker: Mapped[str | None] = mapped_column(String(255))
    voice_text: Mapped[str | None] = mapped_column(Text)
    subtitle_text: Mapped[str | None] = mapped_column(Text)
    visual_description: Mapped[str | None] = mapped_column(Text)
    image_prompt: Mapped[str | None] = mapped_column(Text)
    negative_prompt: Mapped[str | None] = mapped_column(Text)
    characters_json: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    primary_character_id: Mapped[str | None] = mapped_column(String(255))
    location_reference_id: Mapped[int | None] = mapped_column(ForeignKey("reference.id", ondelete="SET NULL"))
    character_batch_key: Mapped[str | None] = mapped_column(String(64))
    audio_start_sec: Mapped[float | None]
    audio_end_sec: Mapped[float | None]
    audio_duration_sec: Mapped[float | None]
    head_padding_sec: Mapped[float] = mapped_column(default=0.0, nullable=False)
    tail_padding_sec: Mapped[float] = mapped_column(default=0.0, nullable=False)
    motion_intent: Mapped[str] = mapped_column(String(32), default="static", nullable=False)
    motion_provider: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    hero_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    camera_motion_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    motion_fill_policy: Mapped[str] = mapped_column(String(16), default="extend", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    episode: Mapped["Episode"] = relationship(back_populates="shots")
    scene: Mapped["Scene | None"] = relationship(back_populates="shots")
    location_reference: Mapped["Reference | None"] = relationship(foreign_keys=[location_reference_id])
    assets: Mapped[list["Asset"]] = relationship(back_populates="shot")
    jobs: Mapped[list["Job"]] = relationship(back_populates="shot")
    qa_notes: Mapped[list["SimpleQaNote"]] = relationship(back_populates="shot")

    @validates("characters_json")
    def validate_characters(self, _key: str, value: list[str] | None) -> list[str]:
        characters = [] if value is None else value
        if not isinstance(characters, list) or any(not isinstance(item, str) or not item for item in characters):
            raise ValueError("characters_json must be a list of non-empty character IDs")
        if len(characters) != len(set(characters)):
            raise ValueError("characters_json may not contain duplicate character IDs")
        return characters

    @validates("primary_character_id")
    def validate_primary_character(self, _key: str, value: str | None) -> str | None:
        characters = self.characters_json or []
        if value is not None and value not in characters:
            raise ValueError("primary_character_id must belong to characters_json")
        if not characters and value is not None:
            raise ValueError("primary_character_id must be null when characters_json is empty")
        return value

    def validate_character_invariants(self) -> None:
        characters = self.characters_json or []
        if self.primary_character_id is not None and self.primary_character_id not in characters:
            raise ValueError("primary_character_id must belong to characters_json")
        if not characters and self.primary_character_id is not None:
            raise ValueError("primary_character_id must be null when characters_json is empty")


@event.listens_for(Session, "before_flush")
def validate_shot_invariants_before_flush(session: Session, _flush_context, _instances) -> None:
    for instance in session.new.union(session.dirty):
        if isinstance(instance, Shot):
            instance.validate_character_invariants()
