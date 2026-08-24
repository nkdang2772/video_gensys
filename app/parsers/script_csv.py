from __future__ import annotations

import csv
import io
from pathlib import Path

from app.parsers.common import ParseError, ParsedShot, normalize_records


def parse_text(content: str, *, source: str | Path = "<memory>") -> list[ParsedShot]:
    try:
        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames is None:
            raise ParseError("CSV header is missing", source=source)
        return normalize_records(reader, source=source)
    except csv.Error as exc:
        raise ParseError(f"Invalid CSV: {exc}", source=source) from exc


def parse_file(path: str | Path, *, encoding: str = "utf-8-sig") -> list[ParsedShot]:
    source = Path(path)
    try:
        content = source.read_text(encoding=encoding)
    except (OSError, UnicodeError) as exc:
        raise ParseError(f"Could not read script: {exc}", source=source) from exc
    return parse_text(content, source=source)

