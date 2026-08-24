from __future__ import annotations

import hashlib
import re
import shutil
import unicodedata
from pathlib import Path

from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from app.models import Reference, ReferenceVersion, Series
from app.services.errors import (
    DuplicateReferenceSlugError,
    ImmutableReferenceVersionError,
    ReferenceNotFoundError,
    ReferenceVersionError,
    SeriesNotFoundError,
)
from app.services.series import slugify

REFERENCE_TYPES = {"character", "style", "location", "prop", "map"}
REFERENCE_SCOPES = {"series_specific", "shared_across_series"}
TYPE_FOLDERS = {
    "character": "characters",
    "style": "styles",
    "location": "locations",
    "prop": "props",
    "map": "maps",
}
IMMUTABLE_VERSION_FIELDS = {
    "reference_id",
    "version",
    "file_path",
    "descriptor_json",
    "checksum",
    "created_at",
}


def normalize_reference_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.replace("Đ", "D").replace("đ", "d"))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    clean = re.sub(r"[^a-z0-9_-]+", "-", ascii_value)
    clean = re.sub(r"-+", "-", clean).strip("-_")
    if not clean:
        raise ValueError("A reference slug cannot be generated from the supplied value")
    return clean


@event.listens_for(Session, "before_flush")
def prevent_reference_version_updates(session: Session, _flush_context, _instances) -> None:
    for instance in session.dirty:
        if not isinstance(instance, ReferenceVersion):
            continue
        state = inspect(instance)
        changed = [
            field for field in IMMUTABLE_VERSION_FIELDS if state.attrs[field].history.has_changes()
        ]
        if changed:
            raise ImmutableReferenceVersionError(
                "ReferenceVersion is immutable; changed fields: " + ", ".join(sorted(changed))
            )


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _get_reference(session: Session, reference_id: int) -> Reference:
    reference = session.get(Reference, reference_id)
    if reference is None:
        raise ReferenceNotFoundError(f"Reference not found: {reference_id}")
    return reference


def create_reference(
    session: Session,
    *,
    name: str,
    reference_type: str,
    scope: str = "series_specific",
    owning_series_id: int | None = None,
    slug: str | None = None,
    is_active: bool = True,
) -> Reference:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Reference name cannot be empty")
    clean_type = reference_type.strip().lower()
    clean_scope = scope.strip().lower()
    if clean_type not in REFERENCE_TYPES:
        raise ValueError(f"Unsupported reference_type: {reference_type}")
    if clean_scope not in REFERENCE_SCOPES:
        raise ValueError(f"Unsupported reference scope: {scope}")
    if clean_scope == "series_specific":
        if owning_series_id is None:
            raise ValueError("series_specific reference requires owning_series_id")
        series = session.scalar(
            select(Series).where(Series.id == owning_series_id, Series.deleted_at.is_(None))
        )
        if series is None:
            raise SeriesNotFoundError(f"Series not found: {owning_series_id}")
    elif owning_series_id is not None:
        raise ValueError("shared_across_series reference must not have owning_series_id")

    clean_slug = normalize_reference_slug(slug) if slug is not None else slugify(clean_name)
    if session.scalar(select(Reference.id).where(Reference.slug == clean_slug).limit(1)) is not None:
        raise DuplicateReferenceSlugError(f"Reference slug already exists: {clean_slug}")
    reference = Reference(
        slug=clean_slug,
        name=clean_name,
        reference_type=clean_type,
        scope=clean_scope,
        owning_series_id=owning_series_id,
        current_version=0,
        is_active=is_active,
    )
    session.add(reference)
    try:
        session.flush()
    except IntegrityError as exc:
        raise DuplicateReferenceSlugError(f"Reference slug already exists: {clean_slug}") from exc
    return reference


def resolve_reference_file(library_root: str | Path, version: ReferenceVersion) -> Path:
    root = Path(library_root).expanduser().resolve()
    candidate = (root / Path(*Path(version.file_path.replace("\\", "/")).parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ReferenceVersionError("ReferenceVersion path escapes library root") from exc
    return candidate


def _relative_destination(reference: Reference, series: Series | None, version: int, suffix: str) -> Path:
    type_folder = TYPE_FOLDERS[reference.reference_type]
    filename = f"{reference.slug}_v{version:03d}{suffix.lower()}"
    if reference.scope == "shared_across_series":
        return Path("references_shared") / type_folder / reference.slug / filename
    if series is None:
        raise ReferenceVersionError("Series-specific reference has no owning Series")
    return Path("series") / series.slug / "references" / type_folder / reference.slug / filename


def add_version(
    session: Session,
    *,
    reference_id: int,
    source_path: str | Path,
    library_root: str | Path,
    descriptor_json: dict | None = None,
) -> ReferenceVersion:
    if session.in_transaction():
        raise ReferenceVersionError("add_version requires a Session without an active transaction")
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise ReferenceVersionError(f"Reference source file does not exist: {source}")
    root = Path(library_root).expanduser().resolve()
    copied_file: Path | None = None
    try:
        with session.begin():
            reference = _get_reference(session, reference_id)
            series = session.get(Series, reference.owning_series_id) if reference.owning_series_id else None
            latest_version = session.scalar(
                select(func.max(ReferenceVersion.version)).where(
                    ReferenceVersion.reference_id == reference.id
                )
            ) or 0
            if reference.current_version != latest_version:
                raise ReferenceVersionError(
                    "Reference current_version does not match persisted version history"
                )
            next_version = latest_version + 1
            relative = _relative_destination(reference, series, next_version, source.suffix)
            destination = (root / relative).resolve()
            try:
                destination.relative_to(root)
            except ValueError as exc:
                raise ReferenceVersionError("Reference destination escapes library root") from exc
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise ReferenceVersionError(f"Reference version file already exists: {destination}")
            shutil.copy2(source, destination)
            copied_file = destination
            checksum = _checksum(destination)
            version = ReferenceVersion(
                reference=reference,
                version=next_version,
                file_path=relative.as_posix(),
                descriptor_json=descriptor_json,
                checksum=checksum,
            )
            reference.current_version = next_version
            session.add(version)
            session.flush()
        return version
    except Exception as exc:
        if copied_file is not None and copied_file.exists():
            try:
                copied_file.unlink()
            except OSError as cleanup_error:
                raise ReferenceVersionError(
                    f"Version creation failed and copied file could not be removed: {copied_file}"
                ) from cleanup_error
        if isinstance(exc, (ReferenceVersionError, ReferenceNotFoundError)):
            raise
        raise ReferenceVersionError(f"Could not add ReferenceVersion: {exc}") from exc


def list_versions(session: Session, reference_id: int) -> list[ReferenceVersion]:
    _get_reference(session, reference_id)
    return list(
        session.scalars(
            select(ReferenceVersion)
            .where(ReferenceVersion.reference_id == reference_id)
            .order_by(ReferenceVersion.version)
        )
    )


def get_version_by_id(session: Session, version_id: int) -> ReferenceVersion:
    version = session.get(ReferenceVersion, version_id)
    if version is None:
        raise ReferenceVersionError(f"ReferenceVersion not found: {version_id}")
    return version
