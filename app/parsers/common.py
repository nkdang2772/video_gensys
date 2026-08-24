from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

MOTION_INTENTS = {"static", "pan", "parallax", "sprite", "map", "generative"}
SHOT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class ParseError(ValueError):
    def __init__(self, message: str, *, source: str | Path = "<memory>", location: str | int | None = None):
        self.source = str(source)
        self.location = location
        prefix = self.source if location is None else f"{self.source}:{location}"
        super().__init__(f"{prefix}: {message}")


@dataclass(frozen=True, slots=True)
class ParsedShot:
    scene: str | None
    shot_id: str
    speaker: str | None
    text: str
    visual_description: str
    motion_intent: str


def _value(record: Mapping[str, Any], *names: str) -> Any:
    normalized = {str(key).strip().lower(): value for key, value in record.items() if key is not None}
    for name in names:
        if name in normalized:
            return normalized[name]
    return None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def normalize_records(
    records: Iterable[Mapping[str, Any]], *, source: str | Path = "<memory>"
) -> list[ParsedShot]:
    shots: list[ParsedShot] = []
    seen: dict[str, int] = {}
    for index, record in enumerate(records, start=1):
        if not isinstance(record, Mapping):
            raise ParseError("Each shot must be an object/row", source=source, location=index)
        if not any(_text(value) for value in record.values() if value is not None):
            continue

        raw_shot_id = _text(_value(record, "shot_id", "shot"))
        if not raw_shot_id:
            raise ParseError("Missing shot_id", source=source, location=index)
        shot_id = raw_shot_id.lower()
        if not SHOT_ID_PATTERN.fullmatch(shot_id):
            raise ParseError(
                "shot_id may only contain letters, numbers, '_' and '-'",
                source=source,
                location=index,
            )
        if shot_id in seen:
            raise ParseError(
                f"Duplicate shot_id {shot_id!r}; first seen at record {seen[shot_id]}",
                source=source,
                location=index,
            )
        seen[shot_id] = index

        motion_intent = _text(_value(record, "motion_intent")) or "static"
        motion_intent = motion_intent.lower()
        if motion_intent not in MOTION_INTENTS:
            raise ParseError(
                f"Invalid motion_intent {motion_intent!r}", source=source, location=index
            )

        scene = _text(_value(record, "scene", "scene_id", "scene_number")) or None
        speaker = _text(_value(record, "speaker")) or None
        shots.append(
            ParsedShot(
                scene=scene,
                shot_id=shot_id,
                speaker=speaker,
                text=_text(_value(record, "text", "voice_text")),
                visual_description=_text(
                    _value(record, "visual", "visual_description")
                ),
                motion_intent=motion_intent,
            )
        )
    return shots
