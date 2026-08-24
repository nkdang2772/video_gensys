from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Series
from app.models.mixins import utc_now
from app.services.errors import DuplicateSeriesSlugError, SeriesNotFoundError

UPDATABLE_FIELDS = {
    "name",
    "description",
    "default_resolution",
    "default_fps",
    "default_aspect_ratio",
    "style_anchor_reference_id",
    "palette_json",
    "font_config_json",
}


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.replace("Đ", "D").replace("đ", "d"))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    if not slug:
        raise ValueError("A slug cannot be generated from the supplied value")
    return slug


def _slug_exists(session: Session, slug: str, *, excluding_id: int | None = None) -> bool:
    statement = select(Series.id).where(Series.slug == slug)
    if excluding_id is not None:
        statement = statement.where(Series.id != excluding_id)
    return session.scalar(statement.limit(1)) is not None


def create_series(
    session: Session,
    *,
    name: str,
    slug: str | None = None,
    description: str | None = None,
    default_resolution: str = "1920x1080",
    default_fps: float = 30.0,
    default_aspect_ratio: str = "16:9",
    palette_json: dict[str, Any] | None = None,
    font_config_json: dict[str, Any] | None = None,
) -> Series:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Series name cannot be empty")
    clean_slug = slugify(slug or clean_name)
    if _slug_exists(session, clean_slug):
        raise DuplicateSeriesSlugError(f"Series slug already exists: {clean_slug}")

    series = Series(
        slug=clean_slug,
        name=clean_name,
        description=description,
        default_resolution=default_resolution,
        default_fps=default_fps,
        default_aspect_ratio=default_aspect_ratio,
        palette_json=palette_json,
        font_config_json=font_config_json,
    )
    session.add(series)
    try:
        session.flush()
    except IntegrityError as exc:
        raise DuplicateSeriesSlugError(f"Series slug already exists: {clean_slug}") from exc
    return series


def list_series(session: Session, *, include_deleted: bool = False) -> list[Series]:
    statement = select(Series).order_by(Series.created_at, Series.id)
    if not include_deleted:
        statement = statement.where(Series.deleted_at.is_(None))
    return list(session.scalars(statement))


def get_series_by_id(
    session: Session, series_id: int, *, include_deleted: bool = False
) -> Series:
    statement = select(Series).where(Series.id == series_id)
    if not include_deleted:
        statement = statement.where(Series.deleted_at.is_(None))
    series = session.scalar(statement)
    if series is None:
        raise SeriesNotFoundError(f"Series not found: {series_id}")
    return series


def update_series(session: Session, series_id: int, **changes: Any) -> Series:
    unknown = set(changes) - UPDATABLE_FIELDS - {"slug"}
    if unknown:
        raise ValueError(f"Unsupported Series fields: {', '.join(sorted(unknown))}")
    series = get_series_by_id(session, series_id)

    validated_changes = dict(changes)
    clean_slug: str | None = None
    if "name" in validated_changes:
        clean_name = str(validated_changes["name"]).strip()
        if not clean_name:
            raise ValueError("Series name cannot be empty")
        validated_changes["name"] = clean_name
    if "slug" in validated_changes:
        clean_slug = slugify(str(validated_changes.pop("slug")))
        if _slug_exists(session, clean_slug, excluding_id=series.id):
            raise DuplicateSeriesSlugError(f"Series slug already exists: {clean_slug}")

    if clean_slug is not None:
        series.slug = clean_slug
    for field, value in validated_changes.items():
        setattr(series, field, value)
    try:
        session.flush()
    except IntegrityError as exc:
        raise DuplicateSeriesSlugError(f"Series slug already exists: {series.slug}") from exc
    return series


def soft_delete_series(session: Session, series_id: int) -> Series:
    series = get_series_by_id(session, series_id)
    series.deleted_at = utc_now()
    session.flush()
    return series
