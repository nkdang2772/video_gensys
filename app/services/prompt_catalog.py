from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Reference
from app.services.reference import create_reference, normalize_reference_slug

CATALOG_LINE = re.compile(r"^\s*(Char|Bg)\(([^)]+)\)\s*:\s*(.+?)\s*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PromptCatalogEntry:
    slug: str
    reference_type: str
    prompt: str
    aliases: tuple[str, ...]


def _default_aliases(slug: str) -> tuple[str, ...]:
    words = [word for word in slug.replace("-", "_").split("_") if word]
    if words and words[0] in {"bg", "char", "character", "location"}:
        words = words[1:]
    phrase = " ".join(words)
    return tuple(dict.fromkeys(value for value in (slug, phrase) if value))


def parse_prompt_catalog(text: str, *, source: str = "prompt catalog") -> list[PromptCatalogEntry]:
    entries: list[PromptCatalogEntry] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = CATALOG_LINE.match(raw)
        if match is None:
            raise ValueError(f"{source}:{line_number}: expected Char(key): prompt or Bg(key): prompt")
        kind, raw_slug, prompt = match.groups()
        slug = normalize_reference_slug(raw_slug)
        if slug in seen:
            raise ValueError(f"{source}:{line_number}: duplicate reference key {slug!r}")
        seen.add(slug)
        entries.append(
            PromptCatalogEntry(
                slug=slug,
                reference_type="character" if kind.lower() == "char" else "location",
                prompt=prompt.strip(),
                aliases=_default_aliases(slug),
            )
        )
    if not entries:
        raise ValueError(f"{source}: no prompt entries found")
    return entries


def import_prompt_catalog(
    session: Session, *, series_id: int, entries: list[PromptCatalogEntry]
) -> tuple[list[Reference], int]:
    references: list[Reference] = []
    created = 0
    for entry in entries:
        reference = session.scalar(select(Reference).where(Reference.slug == entry.slug))
        if reference is None:
            reference = create_reference(
                session,
                name=entry.slug.replace("_", " ").replace("-", " ").title(),
                slug=entry.slug,
                reference_type=entry.reference_type,
                scope="series_specific",
                owning_series_id=series_id,
            )
            created += 1
        elif (
            reference.owning_series_id != series_id
            or reference.scope != "series_specific"
            or reference.reference_type != entry.reference_type
        ):
            raise ValueError(f"Reference slug {entry.slug!r} already belongs to another scope/type")
        reference.generation_prompt = entry.prompt
        reference.aliases_json = list(entry.aliases)
        references.append(reference)
    session.flush()
    return references, created
