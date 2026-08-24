from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.parsers.common import ParseError, ParsedShot, normalize_records

TAG_PATTERN = re.compile(
    r"^\s*\[(SCENE|SHOT|SPEAKER|TEXT|VISUAL|MOTION_INTENT)\s*:\s*(.*?)\]\s*$",
    re.IGNORECASE,
)
SHOT_TAGS = {"SPEAKER", "TEXT", "VISUAL", "MOTION_INTENT"}
MULTILINE_TAGS = {"TEXT", "VISUAL"}


def parse_text(content: str, *, source: str | Path = "<memory>") -> list[ParsedShot]:
    records: list[dict[str, Any]] = []
    current_scene: str | None = None
    current_shot: dict[str, Any] | None = None
    active_multiline_field: str | None = None

    def finish_current() -> None:
        nonlocal current_shot, active_multiline_field
        if current_shot is not None:
            records.append(current_shot)
        current_shot = None
        active_multiline_field = None

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        match = TAG_PATTERN.match(raw_line)
        if match:
            tag, value = match.group(1).upper(), match.group(2).strip()
            if tag == "SCENE":
                finish_current()
                current_scene = value or None
                continue
            if tag == "SHOT":
                finish_current()
                if not value:
                    raise ParseError("Missing shot_id", source=source, location=line_number)
                current_shot = {"scene": current_scene, "shot_id": value}
                continue
            if tag in SHOT_TAGS and current_shot is None:
                raise ParseError(
                    f"{tag} appears before a SHOT tag",
                    source=source,
                    location=line_number,
                )

            assert current_shot is not None
            field = {
                "SPEAKER": "speaker",
                "TEXT": "text",
                "VISUAL": "visual",
                "MOTION_INTENT": "motion_intent",
            }[tag]
            if tag in MULTILINE_TAGS:
                previous = current_shot.get(field, "")
                current_shot[field] = "\n".join(part for part in (previous, value) if part)
                active_multiline_field = field
            else:
                current_shot[field] = value
                active_multiline_field = None
            continue

        stripped = raw_line.strip()
        if not stripped:
            if current_shot is not None and active_multiline_field and current_shot.get(active_multiline_field):
                current_shot[active_multiline_field] += "\n"
            continue
        if current_shot is None:
            raise ParseError(
                "Content appears outside a SHOT block", source=source, location=line_number
            )
        if active_multiline_field is None:
            raise ParseError(
                "Untagged content is only allowed after TEXT or VISUAL",
                source=source,
                location=line_number,
            )
        current_shot[active_multiline_field] = (
            current_shot.get(active_multiline_field, "") + "\n" + stripped
        )

    finish_current()
    return normalize_records(records, source=source)


def parse_file(path: str | Path, *, encoding: str = "utf-8-sig") -> list[ParsedShot]:
    source = Path(path)
    try:
        content = source.read_text(encoding=encoding)
    except (OSError, UnicodeError) as exc:
        raise ParseError(f"Could not read script: {exc}", source=source) from exc
    return parse_text(content, source=source)
