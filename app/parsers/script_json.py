from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.parsers.common import ParseError, ParsedShot, normalize_records


def parse_text(content: str, *, source: str | Path = "<memory>") -> list[ParsedShot]:
    try:
        payload: Any = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ParseError(
            f"Invalid JSON: {exc.msg}", source=source, location=exc.lineno
        ) from exc
    if isinstance(payload, dict):
        payload = payload.get("shots")
    if not isinstance(payload, list):
        raise ParseError("JSON root must be a list or an object with a 'shots' list", source=source)
    return normalize_records(payload, source=source)


def parse_file(path: str | Path, *, encoding: str = "utf-8-sig") -> list[ParsedShot]:
    source = Path(path)
    try:
        content = source.read_text(encoding=encoding)
    except (OSError, UnicodeError) as exc:
        raise ParseError(f"Could not read script: {exc}", source=source) from exc
    return parse_text(content, source=source)

