from __future__ import annotations

import tempfile
from dataclasses import asdict
from pathlib import Path

import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Episode, Shot
from app.parsers.common import ParseError, ParsedShot
from app.parsers.dispatcher import parse_script_file, parse_script_text
from app.services.errors import DomainError
from app.services.import_script import import_parsed_script
from app.services.import_voice import import_voice_folder


def _selected_episode(session_factory: sessionmaker[Session]) -> Episode | None:
    episode_id = st.session_state.get("selected_episode_id")
    if episode_id is None:
        return None
    with session_factory() as session:
        return session.get(Episode, episode_id)


def _load_script(uploaded, local_path: str) -> tuple[list[ParsedShot], str, bytes]:
    if uploaded is not None:
        raw = uploaded.getvalue()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ParseError("Uploaded script must use UTF-8", source=uploaded.name) from exc
        return parse_script_text(text, filename=uploaded.name, source=uploaded.name), uploaded.name, raw
    if local_path.strip():
        path = Path(local_path).expanduser().resolve()
        raw = path.read_bytes()
        return parse_script_file(path), path.name, raw
    raise ParseError("Choose a script file or enter a local script path")


def render(session_factory: sessionmaker[Session]) -> None:
    st.header("Import script and voice")
    episode = _selected_episode(session_factory)
    if episode is None:
        st.info("Open an Episode first.")
        return
    st.caption(f"Episode: {episode.title} — {episode.root_path}")

    uploaded_script = st.file_uploader(
        "Script file", type=["txt", "csv", "json"], key="import_script_upload"
    )
    local_script_path = st.text_input(
        "Or local script path", key="import_script_path", help="Desktop/local mode"
    )
    preview_clicked = st.button("Preview script", key="import_preview_button")
    import_clicked = st.button("Import script", type="primary", key="import_script_button")
    planned_duration = st.number_input(
        "Initial visual duration per shot (seconds)", min_value=0.1, value=4.0, step=0.5,
        key="import_planned_duration",
    )
    if preview_clicked or import_clicked:
        try:
            parsed, source_name, source_bytes = _load_script(uploaded_script, local_script_path)
            st.session_state.script_preview = [asdict(shot) for shot in parsed]
            if import_clicked:
                with session_factory() as session:
                    imported = import_parsed_script(
                        session,
                        episode_id=episode.id,
                        parsed_shots=parsed,
                        source_name=source_name,
                        source_bytes=source_bytes,
                        planned_duration_sec=float(planned_duration),
                    )
                st.success(f"Imported {len(imported)} shots")
        except (DomainError, ParseError, ValueError, OSError) as exc:
            st.error(str(exc))

    preview = st.session_state.get("script_preview")
    if preview:
        st.subheader("Parsed preview")
        st.dataframe(preview, use_container_width=True, hide_index=True)

    st.subheader("Voice WAV")
    voice_folder = st.text_input("Local WAV folder", key="import_voice_folder")
    uploaded_wavs = st.file_uploader(
        "Or select multiple WAV files",
        type=["wav"],
        accept_multiple_files=True,
        key="import_voice_uploads",
    )
    if st.button("Link and import voice", key="import_voice_button"):
        try:
            if voice_folder.strip():
                with session_factory() as session:
                    report = import_voice_folder(
                        session, episode_id=episode.id, folder=voice_folder.strip()
                    )
            elif uploaded_wavs:
                with tempfile.TemporaryDirectory(prefix="video-gensystem-voice-") as temporary:
                    staging = Path(temporary)
                    staged_names: set[str] = set()
                    for uploaded in uploaded_wavs:
                        safe_name = Path(uploaded.name).name
                        normalized_name = safe_name.lower()
                        if normalized_name in staged_names:
                            raise ValueError(f"Duplicate uploaded WAV filename: {safe_name}")
                        staged_names.add(normalized_name)
                        (staging / safe_name).write_bytes(uploaded.getvalue())
                    with session_factory() as session:
                        report = import_voice_folder(
                            session, episode_id=episode.id, folder=staging
                        )
            else:
                raise ValueError("Enter a local WAV folder or select WAV files")
            st.success(f"Imported {len(report.imported_assets)} audio assets")
            for warning in report.warnings:
                st.warning(f"{warning.code}: {warning.message}")
        except (DomainError, ValueError, OSError) as exc:
            st.error(str(exc))

    with session_factory() as session:
        shots = list(
            session.scalars(
                select(Shot).where(Shot.episode_id == episode.id).order_by(Shot.order_index)
            )
        )
        rows = [
            {
                "shot_id": shot.shot_id,
                "scene": shot.scene.title if shot.scene else None,
                "speaker": shot.speaker,
                "text": shot.voice_text,
                "visual": shot.visual_description,
                "motion": shot.motion_intent,
                "audio_duration": shot.audio_duration_sec,
                "planned_duration": shot.planned_duration_sec,
            }
            for shot in shots
        ]
    if rows:
        st.subheader("Episode shot list")
        st.dataframe(rows, use_container_width=True, hide_index=True)
