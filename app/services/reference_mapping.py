from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Episode, EpisodeReferencePin, Reference, ReferenceVersion, Shot
from app.services.character_batch import compute_batch_key


def _normalized(value: str | None) -> str:
    raw = (value or "").replace("Đ", "D").replace("đ", "d")
    ascii_value = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", ascii_value))


def _matches(text: str, reference: Reference) -> bool:
    candidates = [reference.slug, reference.name, *(reference.aliases_json or [])]
    normalized_text = f" {text} "
    text_tokens = set(text.split())
    for alias in candidates:
        normalized_alias = _normalized(alias)
        if not normalized_alias:
            continue
        if f" {normalized_alias} " in normalized_text:
            return True
        alias_tokens = {token for token in normalized_alias.split() if len(token) > 2}
        if len(alias_tokens) >= 2 and len(alias_tokens & text_tokens) / len(alias_tokens) >= 0.6:
            return True
    return False


@dataclass(frozen=True, slots=True)
class MappingReport:
    shot_count: int
    character_mapped: int
    location_mapped: int
    unmapped_shot_ids: tuple[str, ...]


def auto_map_episode_references(session: Session, episode_id: int) -> MappingReport:
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise ValueError(f"Episode not found: {episode_id}")
    pinned_reference_ids = set(
        session.scalars(
            select(EpisodeReferencePin.reference_id).where(
                EpisodeReferencePin.episode_id == episode_id
            )
        )
    )
    references = list(
        session.scalars(
            select(Reference).where(
                Reference.is_active.is_(True),
                or_(
                    Reference.owning_series_id == episode.series_id,
                    Reference.id.in_(pinned_reference_ids),
                ),
            )
        )
    )
    characters = [item for item in references if item.reference_type == "character"]
    locations = [item for item in references if item.reference_type == "location"]
    shots = list(session.scalars(select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.order_index)))
    character_count = location_count = 0
    unmapped: list[str] = []
    for shot in shots:
        text = _normalized(" ".join(filter(None, (shot.speaker, shot.voice_text, shot.visual_description))))
        matched_characters = [item.slug for item in characters if _matches(text, item)]
        matched_locations = [item for item in locations if _matches(text, item)]
        shot.characters_json = matched_characters
        shot.character_batch_key = compute_batch_key(matched_characters)
        speaker_text = _normalized(shot.speaker)
        primary = next((item.slug for item in characters if _matches(speaker_text, item)), None)
        shot.primary_character_id = primary if primary in matched_characters else None
        shot.location_reference_id = matched_locations[0].id if len(matched_locations) == 1 else None
        character_count += bool(matched_characters)
        location_count += shot.location_reference_id is not None
        if not matched_characters and shot.location_reference_id is None:
            unmapped.append(shot.shot_id)
    session.flush()
    return MappingReport(len(shots), character_count, location_count, tuple(unmapped))


def sync_episode_reference_pins(
    session: Session, episode_id: int, *, update_existing: bool = False
) -> tuple[int, int]:
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise ValueError(f"Episode not found: {episode_id}")
    style_anchor_id = episode.series.style_anchor_reference_id
    references = list(
        session.scalars(
            select(Reference).where(
                Reference.is_active.is_(True),
                Reference.current_version > 0,
                or_(
                    Reference.owning_series_id == episode.series_id,
                    Reference.id == style_anchor_id,
                ),
            )
        )
    )
    existing = {
        pin.reference_id: pin
        for pin in session.scalars(select(EpisodeReferencePin).where(EpisodeReferencePin.episode_id == episode_id))
    }
    added = updated = 0
    for reference in references:
        version = session.scalar(
            select(ReferenceVersion).where(
                ReferenceVersion.reference_id == reference.id,
                ReferenceVersion.version == reference.current_version,
            )
        )
        if version is None:
            continue
        pin = existing.get(reference.id)
        if pin is None:
            session.add(EpisodeReferencePin(episode_id=episode_id, reference_id=reference.id, reference_version_id=version.id))
            added += 1
        elif update_existing and pin.reference_version_id != version.id:
            pin.reference_version_id = version.id
            updated += 1
    session.flush()
    return added, updated
