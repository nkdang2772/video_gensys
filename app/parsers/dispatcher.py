from __future__ import annotations

from pathlib import Path

from app.parsers.common import ParseError, ParsedShot
from app.parsers import script_csv, script_json, script_txt


def parse_script_text(
    content: str, *, filename: str = "script.txt", source: str | Path = "<memory>"
) -> list[ParsedShot]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        return script_txt.parse_text(content, source=source)
    if suffix == ".csv":
        return script_csv.parse_text(content, source=source)
    if suffix == ".json":
        return script_json.parse_text(content, source=source)
    raise ParseError(f"Unsupported script extension: {suffix or '<none>'}", source=source)

def parse_script_file(path: str | Path) -> list[ParsedShot]:
    source = Path(path).expanduser().resolve()
    suffix = source.suffix.lower()
    if suffix == ".txt":
        return script_txt.parse_file(source)
    if suffix == ".csv":
        return script_csv.parse_file(source)
    if suffix == ".json":
        return script_json.parse_file(source)
    raise ParseError(f"Unsupported script extension: {suffix or '<none>'}", source=source)
