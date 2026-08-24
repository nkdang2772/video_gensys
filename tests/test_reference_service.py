from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.services.errors import ImmutableReferenceVersionError
from app.services.reference import (
    add_version,
    create_reference,
    get_version_by_id,
    list_versions,
    resolve_reference_file,
)
from app.services.series import create_series


def test_create_series_specific_and_shared_references(session) -> None:
    series = create_series(session, name="Any Series")
    session.commit()
    character = create_reference(
        session,
        name="Main Character",
        reference_type="character",
        scope="series_specific",
        owning_series_id=series.id,
    )
    shared_style = create_reference(
        session,
        name="Shared Watercolor",
        reference_type="style",
        scope="shared_across_series",
    )
    session.commit()
    assert character.owning_series_id == series.id
    assert shared_style.owning_series_id is None


def test_add_three_immutable_versions_with_checksums(session, tmp_path: Path) -> None:
    reference = create_reference(
        session,
        name="Generic Character",
        reference_type="character",
        scope="shared_across_series",
    )
    session.commit()

    created = []
    for number in range(1, 4):
        source = tmp_path / f"source_v{number}.png"
        source.write_bytes(f"image-version-{number}".encode())
        created.append(
            add_version(
                session,
                reference_id=reference.id,
                source_path=source,
                library_root=tmp_path / "library",
                descriptor_json={"label": f"v{number}"},
            )
        )

    versions = list_versions(session, reference.id)
    assert [version.version for version in versions] == [1, 2, 3]
    assert reference.current_version == 3
    for version in versions:
        stored = resolve_reference_file(tmp_path / "library", version)
        assert stored.is_file()
        assert version.checksum == hashlib.sha256(stored.read_bytes()).hexdigest()
    assert get_version_by_id(session, created[1].id) is created[1]


def test_source_changes_do_not_modify_old_version_file(session, tmp_path: Path) -> None:
    reference = create_reference(
        session,
        name="Reusable Prop",
        reference_type="prop",
        scope="shared_across_series",
    )
    session.commit()
    source = tmp_path / "source.bin"
    source.write_bytes(b"version-one")
    version = add_version(
        session,
        reference_id=reference.id,
        source_path=source,
        library_root=tmp_path / "library",
    )
    stored = resolve_reference_file(tmp_path / "library", version)
    source.write_bytes(b"source-was-modified")
    assert stored.read_bytes() == b"version-one"


def test_reference_version_record_cannot_be_updated(session, tmp_path: Path) -> None:
    reference = create_reference(
        session,
        name="Immutable Style",
        reference_type="style",
        scope="shared_across_series",
    )
    session.commit()
    source = tmp_path / "style.png"
    source.write_bytes(b"style-v1")
    version = add_version(
        session,
        reference_id=reference.id,
        source_path=source,
        library_root=tmp_path / "library",
    )
    version.file_path = "changed.png"
    with pytest.raises(ImmutableReferenceVersionError):
        session.flush()
    session.rollback()


def test_invalid_reference_scope_ownership_is_rejected(session) -> None:
    with pytest.raises(ValueError, match="requires owning_series_id"):
        create_reference(
            session,
            name="Invalid",
            reference_type="character",
            scope="series_specific",
        )


def test_explicit_reference_slug_preserves_underscore(session) -> None:
    reference = create_reference(
        session,
        name="Character Example",
        slug="character_example",
        reference_type="character",
        scope="shared_across_series",
    )
    session.commit()
    assert reference.slug == "character_example"
