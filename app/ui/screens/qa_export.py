from __future__ import annotations

from pathlib import Path

import streamlit as st
from sqlalchemy.orm import Session, sessionmaker

from app.export.package import export_episode_package
from app.qa.checker import run_asset_checks


def render(session_factory: sessionmaker[Session], library_root: Path) -> None:
    del library_root
    st.header("QA & Export")
    episode_id = st.session_state.get("selected_episode_id")
    if episode_id is None:
        st.info("Open an Episode first.")
        return
    if st.button("Run asset checker", type="primary"):
        try:
            with session_factory() as session:
                report = run_asset_checks(session, episode_id)
            st.session_state["qa_report"] = report
        except (ValueError, OSError, RuntimeError) as exc:
            st.error(str(exc))
    report = st.session_state.get("qa_report")
    if report is not None and report.episode_id == episode_id:
        status = "PASS" if report.passed else "FAIL"
        st.metric("Automatic QA", status, f"{report.error_count} errors · {report.warning_count} warnings")
        if report.placeholder_shot_ids:
            st.warning("Placeholders: " + ", ".join(report.placeholder_shot_ids))
        if report.html_path:
            st.caption(f"HTML: {report.html_path}")
        if report.json_path:
            st.caption(f"JSON: {report.json_path}")
        for issue in report.issues:
            message = f"[{issue.code}] {issue.shot_id or 'episode'}: {issue.message}"
            st.error(message) if issue.severity == "error" else st.warning(message)
    st.subheader("DaVinci Resolve package")
    allow_errors = st.checkbox("Allow export with QA errors", value=False)
    archive_previous = st.checkbox("Archive previous export before rebuilding", value=False)
    if st.button("Build export package"):
        try:
            with session_factory() as session:
                result = export_episode_package(
                    session, episode_id, allow_qa_errors=allow_errors, force=archive_previous
                )
            st.success(f"Exported {result.shot_count} shots / {result.media_file_count} files")
            st.code(str(result.export_path))
        except (ValueError, OSError, RuntimeError) as exc:
            st.error(str(exc))
