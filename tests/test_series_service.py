from __future__ import annotations

import pytest

from app.services.errors import DuplicateSeriesSlugError, SeriesNotFoundError
from app.services.series import (
    create_series,
    get_series_by_id,
    list_series,
    soft_delete_series,
    update_series,
)


def test_create_series_generates_global_slug(session) -> None:
    series = create_series(session, name="Tam Quốc")
    session.commit()
    assert series.id is not None
    assert series.slug == "tam-quoc"
    assert series.default_resolution == "1920x1080"


def test_list_series_excludes_soft_deleted_by_default(session) -> None:
    active = create_series(session, name="Active")
    deleted = create_series(session, name="Deleted")
    session.commit()
    soft_delete_series(session, deleted.id)
    session.commit()
    assert list_series(session) == [active]
    assert list_series(session, include_deleted=True) == [active, deleted]


def test_get_series_by_id_hides_deleted_series(session) -> None:
    series = create_series(session, name="Tam Quốc")
    session.commit()
    soft_delete_series(session, series.id)
    session.commit()
    with pytest.raises(SeriesNotFoundError):
        get_series_by_id(session, series.id)
    assert get_series_by_id(session, series.id, include_deleted=True) is series


def test_update_series_changes_allowed_fields(session) -> None:
    series = create_series(session, name="Old name")
    session.commit()
    updated = update_series(
        session,
        series.id,
        name="New name",
        slug="new-slug",
        default_fps=24.0,
        palette_json={"primary": "#112233"},
    )
    session.commit()
    assert updated.name == "New name"
    assert updated.slug == "new-slug"
    assert updated.default_fps == 24.0


def test_update_series_validation_error_does_not_leave_partial_changes(session) -> None:
    series = create_series(session, name="Original name", slug="original-slug")
    session.commit()

    with pytest.raises(ValueError, match="name cannot be empty"):
        update_series(session, series.id, slug="unexpected-slug", name="   ")

    session.commit()
    session.refresh(series)
    assert series.name == "Original name"
    assert series.slug == "original-slug"


def test_slug_stays_globally_unique_after_soft_delete(session) -> None:
    series = create_series(session, name="Tam Quốc")
    session.commit()
    soft_delete_series(session, series.id)
    session.commit()
    with pytest.raises(DuplicateSeriesSlugError):
        create_series(session, name="Tam Quoc")
