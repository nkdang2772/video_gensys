from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Episode, Shot
from app.services.character_batch import compute_batch_key
from app.services.errors import DuplicateShotIdError, ShotNotFoundError

UPDATABLE_FIELDS = {
    "scene_id",
    "shot_id",
    "order_index",
    "speaker",
    "voice_text",
    "subtitle_text",
    "visual_description",
    "image_prompt",
    "negative_prompt",
    "characters_json",
    "primary_character_id",
    "location_reference_id",
    "audio_start_sec",
    "audio_end_sec",
    "audio_duration_sec",
    "head_padding_sec",
    "tail_padding_sec",
    "motion_intent",
    "motion_provider",
    "hero_flag",
    "camera_motion_json",
    "motion_fill_policy",
    "status",
    "notes",
}
SHOT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _normalize_characters(value: list[str] | tuple[str, ...]) -> list[str]:
    characters = list(value)
    if any(not isinstance(character, str) or not character for character in characters):
        raise ValueError("characters_json must contain non-empty string IDs")
    if len(characters) != len(set(characters)):
        raise ValueError("characters_json may not contain duplicate character IDs")
    return characters


def _get_shot(session: Session, shot_pk: int) -> Shot:
    shot = session.get(Shot, shot_pk)
    if shot is None:
        raise ShotNotFoundError(f"Shot not found: {shot_pk}")
    return shot


def create_shot(
    session: Session,
    *,
    episode_id: int,
    shot_id: str,
    order_index: int,
    characters_json: list[str] | tuple[str, ...] = (),
    primary_character_id: str | None = None,
    **fields: Any,
) -> Shot:
    if session.get(Episode, episode_id) is None:
        raise ValueError(f"Episode not found: {episode_id}")
    clean_shot_id = shot_id.strip().lower()
    if not SHOT_ID_PATTERN.fullmatch(clean_shot_id):
        raise ValueError("shot_id may only contain letters, numbers, '_' and '-'")
    if session.scalar(
        select(Shot.id).where(Shot.episode_id == episode_id, Shot.shot_id == clean_shot_id).limit(1)
    ) is not None:
        raise DuplicateShotIdError(f"Duplicate shot_id in Episode: {clean_shot_id}")
    unknown = set(fields) - (UPDATABLE_FIELDS - {"shot_id", "order_index", "characters_json", "primary_character_id"})
    if unknown:
        raise ValueError(f"Unsupported Shot fields: {', '.join(sorted(unknown))}")
    characters = _normalize_characters(characters_json)
    shot = Shot(
        episode_id=episode_id,
        shot_id=clean_shot_id,
        order_index=order_index,
        characters_json=characters,
        primary_character_id=primary_character_id,
        character_batch_key=compute_batch_key(characters),
        **fields,
    )
    shot.validate_character_invariants()
    session.add(shot)
    try:
        session.flush()
    except IntegrityError as exc:
        raise DuplicateShotIdError(f"Duplicate shot_id in Episode: {clean_shot_id}") from exc
    return shot


def update_shot(session: Session, shot_pk: int, **changes: Any) -> Shot:
    unknown = set(changes) - UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"Unsupported Shot fields: {', '.join(sorted(unknown))}")
    shot = _get_shot(session, shot_pk)
    if "shot_id" in changes:
        clean_id = str(changes["shot_id"]).strip().lower()
        if not SHOT_ID_PATTERN.fullmatch(clean_id):
            raise ValueError("shot_id may only contain letters, numbers, '_' and '-'")
        duplicate = session.scalar(
            select(Shot.id).where(
                Shot.episode_id == shot.episode_id,
                Shot.shot_id == clean_id,
                Shot.id != shot.id,
            ).limit(1)
        )
        if duplicate is not None:
            raise DuplicateShotIdError(f"Duplicate shot_id in Episode: {clean_id}")
        changes["shot_id"] = clean_id
    try:
        with session.begin_nested():
            if "characters_json" in changes:
                characters = _normalize_characters(changes["characters_json"])
                shot.characters_json = characters
                shot.character_batch_key = compute_batch_key(characters)
                changes.pop("characters_json")
            if "primary_character_id" in changes:
                shot.primary_character_id = changes.pop("primary_character_id")
            for field, value in changes.items():
                setattr(shot, field, value)
            shot.validate_character_invariants()
            session.flush()
    except IntegrityError as exc:
        raise DuplicateShotIdError(f"Duplicate shot_id in Episode: {shot.shot_id}") from exc
    return shot


def bulk_update_shots(session: Session, shot_ids: list[int], **changes: Any) -> list[Shot]:
    if not shot_ids:
        return []
    if len(shot_ids) != len(set(shot_ids)):
        raise ValueError("shot_ids may not contain duplicate primary keys")
    if "shot_id" in changes:
        raise ValueError("shot_id cannot be changed by bulk update")
    unknown = set(changes) - UPDATABLE_FIELDS
    if unknown:
        raise ValueError(f"Unsupported Shot fields: {', '.join(sorted(unknown))}")
    shots = list(session.scalars(select(Shot).where(Shot.id.in_(shot_ids))))
    found_ids = {shot.id for shot in shots}
    missing = sorted(set(shot_ids) - found_ids)
    if missing:
        raise ShotNotFoundError(f"Shots not found: {missing}")
    by_id = {shot.id: shot for shot in shots}
    ordered = [by_id[shot_pk] for shot_pk in shot_ids]
    characters = (
        _normalize_characters(changes["characters_json"])
        if "characters_json" in changes
        else None
    )
    remaining = {
        field: value
        for field, value in changes.items()
        if field not in {"characters_json", "primary_character_id"}
    }
    with session.begin_nested():
        for shot in ordered:
            if characters is not None:
                shot.characters_json = list(characters)
                shot.character_batch_key = compute_batch_key(characters)
            if "primary_character_id" in changes:
                shot.primary_character_id = changes["primary_character_id"]
            for field, value in remaining.items():
                setattr(shot, field, value)
            shot.validate_character_invariants()
        session.flush()
    return ordered
