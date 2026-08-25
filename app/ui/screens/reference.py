from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Episode, Reference, Series
from app.providers.image import GoogleFlowImageProvider, ProviderError
from app.services.errors import DomainError
from app.services.prompt_catalog import import_prompt_catalog, parse_prompt_catalog
from app.services.reference import REFERENCE_TYPES, add_version, create_reference
from app.services.reference_mapping import sync_episode_reference_pins
from app.services.visual_reference import generate_reference_version


def _render_scope(
    session_factory: sessionmaker[Session],
    library_root: Path,
    reference_type: str,
    scope: str,
    series_id: int | None,
) -> None:
    key_prefix = f"reference_{reference_type}_{scope}"
    if scope == "series_specific" and series_id is None:
        st.info("Select a Series to create or view series-specific references.")
        return
    with session_factory() as session:
        statement = select(Reference).where(
            Reference.reference_type == reference_type, Reference.scope == scope
        )
        if scope == "series_specific":
            statement = statement.where(Reference.owning_series_id == series_id)
        references = list(session.scalars(statement.order_by(Reference.name)))
        rows = [
            {
                "id": reference.id,
                "slug": reference.slug,
                "name": reference.name,
                "current_version": reference.current_version,
                "active": reference.is_active,
                "has_prompt": bool(reference.generation_prompt),
            }
            for reference in references
        ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    name = st.text_input("Reference name", key=f"{key_prefix}_name")
    slug = st.text_input("Reference ID/slug (optional)", key=f"{key_prefix}_slug")
    if st.button("Create reference", key=f"{key_prefix}_create"):
        try:
            with session_factory.begin() as session:
                reference = create_reference(
                    session,
                    name=name,
                    slug=slug or None,
                    reference_type=reference_type,
                    scope=scope,
                    owning_series_id=series_id if scope == "series_specific" else None,
                )
                reference_id = reference.id
            st.success(f"Created reference #{reference_id}")
            st.rerun()
        except (DomainError, ValueError) as exc:
            st.error(str(exc))

    if references:
        options = {f"{reference.name} ({reference.slug})": reference.id for reference in references}
        selected = st.selectbox("Reference", list(options), key=f"{key_prefix}_selected")
        selected_reference = next(item for item in references if item.id == options[selected])
        if selected_reference.generation_prompt:
            st.text_area(
                "Generation prompt", value=selected_reference.generation_prompt,
                disabled=True, key=f"{key_prefix}_prompt_preview",
            )
            bridge_port = st.number_input(
                "Google Flow bridge port", min_value=1, max_value=65535, value=8765,
                key=f"{key_prefix}_bridge_port",
            )
            downloads_root = st.text_input(
                "Chrome downloads folder (optional)", key=f"{key_prefix}_downloads_root"
            )
            if st.button("Generate new version with Google Flow", key=f"{key_prefix}_generate_flow"):
                try:
                    config = {"bridge_port": int(bridge_port), "timeout_sec": 900.0}
                    if downloads_root.strip():
                        config["downloads_root"] = downloads_root.strip()
                    with session_factory() as session:
                        version = generate_reference_version(
                            session,
                            reference_id=selected_reference.id,
                            provider=GoogleFlowImageProvider(),
                            library_root=library_root,
                            config=config,
                        )
                    st.success(f"Google Flow image saved as immutable version {version.version}")
                    st.rerun()
                except (DomainError, ProviderError, ValueError, OSError) as exc:
                    st.error(str(exc))
        local_path = st.text_input("Local version file", key=f"{key_prefix}_local_file")
        upload = st.file_uploader("Or upload version", key=f"{key_prefix}_upload")
        if st.button("Add version", key=f"{key_prefix}_add_version"):
            try:
                reference_id = options[selected]
                if local_path.strip():
                    with session_factory() as session:
                        version = add_version(
                            session,
                            reference_id=reference_id,
                            source_path=local_path.strip(),
                            library_root=library_root,
                        )
                elif upload is not None:
                    suffix = Path(upload.name).suffix
                    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
                        temporary.write(upload.getvalue())
                        temporary_path = Path(temporary.name)
                    try:
                        with session_factory() as session:
                            version = add_version(
                                session,
                                reference_id=reference_id,
                                source_path=temporary_path,
                                library_root=library_root,
                            )
                    finally:
                        temporary_path.unlink(missing_ok=True)
                else:
                    raise ValueError("Choose a local file or upload a version")
                st.success(f"Added version {version.version}")
                st.rerun()
            except (DomainError, ValueError, OSError) as exc:
                st.error(str(exc))


def render(session_factory: sessionmaker[Session], library_root: Path) -> None:
    st.header("Reference Library")
    st.caption("References are generic reusable assets. Episode pins are captured when an Episode is created.")
    with session_factory() as session:
        series_rows = list(
            session.scalars(select(Series).where(Series.deleted_at.is_(None)).order_by(Series.name))
        )
    series_options = {f"{series.name} ({series.slug})": series.id for series in series_rows}
    current_id = st.session_state.get("selected_series_id")
    labels = ["<none>", *series_options]
    default = next(
        (index for index, label in enumerate(labels) if series_options.get(label) == current_id), 0
    )
    selected_series = st.selectbox("Series context", labels, index=default, key="reference_series")
    series_id = series_options.get(selected_series)
    if series_id is not None:
        st.session_state.selected_series_id = series_id

        st.subheader("Import visual prompt catalogs")
        st.caption("Supports general Char(key): prompt and Bg(key): prompt files.")
        catalog_path = st.text_input("Prompt catalog path", key="reference_catalog_path")
        if st.button("Import prompt catalog", key="reference_catalog_import"):
            try:
                path = Path(catalog_path).expanduser().resolve()
                entries = parse_prompt_catalog(path.read_text(encoding="utf-8-sig"), source=str(path))
                with session_factory.begin() as session:
                    references, created = import_prompt_catalog(
                        session, series_id=series_id, entries=entries
                    )
                st.success(f"Imported {len(references)} prompts; created {created} references")
                st.rerun()
            except (DomainError, ValueError, OSError) as exc:
                st.error(str(exc))

        episode_id = st.session_state.get("selected_episode_id")
        if episode_id is not None:
            refresh_existing = st.checkbox(
                "Update existing pins to current versions", value=False,
                key="reference_sync_update_existing",
            )
            if st.button("Sync references to open Episode", key="reference_sync_episode"):
                try:
                    with session_factory.begin() as session:
                        episode = session.get(Episode, episode_id)
                        if episode is None or episode.series_id != series_id:
                            raise ValueError("Open Episode does not belong to this Series")
                        added, updated = sync_episode_reference_pins(
                            session, episode_id, update_existing=refresh_existing
                        )
                    st.success(f"Added {added} pins; updated {updated} pins")
                except (DomainError, ValueError) as exc:
                    st.error(str(exc))

    type_tabs = st.tabs([value.title() for value in sorted(REFERENCE_TYPES)])
    for type_tab, reference_type in zip(type_tabs, sorted(REFERENCE_TYPES)):
        with type_tab:
            shared_tab, series_tab = st.tabs(["Shared", "Series-specific"])
            with shared_tab:
                _render_scope(
                    session_factory, library_root, reference_type, "shared_across_series", None
                )
            with series_tab:
                _render_scope(
                    session_factory, library_root, reference_type, "series_specific", series_id
                )
