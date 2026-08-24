from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, Episode, Shot
from app.paths import resolve
from app.qa.checker import QaReport, run_asset_checks

MANIFEST_COLUMNS = (
    "series_slug", "episode_slug", "scene_id", "shot_id", "order_index", "speaker",
    "audio_path", "image_path", "motion_path", "effective_duration_sec", "motion_intent",
    "motion_provider", "hero_flag", "camera_motion_json", "motion_fill_policy", "subtitle_path",
)
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


@dataclass(frozen=True, slots=True)
class ExportResult:
    export_path: Path
    manifest_path: Path
    project_manifest_path: Path
    readme_path: Path
    media_file_count: int
    shot_count: int
    qa_report: QaReport


def _chosen(shot: Shot, kind: str) -> Asset | None:
    return next((asset for asset in shot.assets if asset.asset_type == kind and asset.is_chosen), None)


def _link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _export_asset(episode: Episode, shot: Shot, asset: Asset | None, folder: Path, label: str) -> str:
    if asset is None:
        return ""
    source = resolve(episode, asset.file_path)
    destination = folder / f"{shot.shot_id}_{label}_v{asset.version:02d}_chosen{source.suffix.lower()}"
    _link_or_copy(source, destination)
    return destination.relative_to(folder.parent).as_posix()


def export_episode_package(
    session: Session,
    episode_id: int,
    *,
    ffmpeg_path: str | Path | None = None,
    ffprobe_path: str | Path | None = None,
    allow_qa_errors: bool = False,
    force: bool = False,
) -> ExportResult:
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise ValueError(f"Episode not found: {episode_id}")
    qa_report = run_asset_checks(session, episode_id, ffmpeg_path=ffmpeg_path, ffprobe_path=ffprobe_path)
    if not qa_report.passed and not allow_qa_errors:
        raise ValueError(f"Export blocked by {qa_report.error_count} QA error(s); review {qa_report.html_path}")
    shots = list(session.scalars(select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.order_index, Shot.id)))
    if not shots:
        raise ValueError("Episode has no shots to export")
    for shot in shots:
        if not SAFE_COMPONENT.fullmatch(shot.shot_id):
            raise ValueError(f"Unsafe shot_id for export filename: {shot.shot_id!r}")
    destination = resolve(episode, "export")
    if destination.exists() and any(destination.iterdir()):
        if not force:
            raise FileExistsError(f"Export folder is not empty: {destination}")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup = destination.with_name(f"export_backup_{timestamp}")
        destination.replace(backup)
    destination.mkdir(parents=True, exist_ok=True)
    folders = {name: destination / name for name in ("audio", "images", "clips", "subtitles")}
    for folder in folders.values():
        folder.mkdir(exist_ok=True)
    rows: list[dict[str, object]] = []
    notes: dict[str, str] = {}
    count = 0
    try:
        for shot in shots:
            audio = _export_asset(episode, shot, _chosen(shot, "audio"), folders["audio"], "audio")
            image = _export_asset(episode, shot, _chosen(shot, "image"), folders["images"], "image")
            motion = _export_asset(episode, shot, _chosen(shot, "video"), folders["clips"], "motion")
            subtitle = _export_asset(episode, shot, _chosen(shot, "subtitle"), folders["subtitles"], "subtitle")
            count += sum(bool(item) for item in (audio, image, motion, subtitle))
            if shot.notes:
                notes[shot.shot_id] = shot.notes
            rows.append({
                "series_slug": episode.series.slug,
                "episode_slug": episode.slug,
                "scene_id": shot.scene.scene_number if shot.scene else "",
                "shot_id": shot.shot_id,
                "order_index": shot.order_index,
                "speaker": shot.speaker or "",
                "audio_path": audio,
                "image_path": image,
                "motion_path": motion,
                "effective_duration_sec": f"{float(shot.audio_duration_sec or 0) + float(shot.head_padding_sec or 0) + float(shot.tail_padding_sec or 0):.6f}",
                "motion_intent": shot.motion_intent,
                "motion_provider": shot.motion_provider,
                "hero_flag": "true" if shot.hero_flag else "false",
                "camera_motion_json": json.dumps(shot.camera_motion_json, ensure_ascii=False, sort_keys=True) if shot.camera_motion_json is not None else "",
                "motion_fill_policy": shot.motion_fill_policy,
                "subtitle_path": subtitle,
            })
        manifest = destination / "shot_manifest.csv"
        with manifest.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        project_manifest = destination / "project_manifest.json"
        project_manifest.write_text(json.dumps({
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "series": {"id": episode.series_id, "slug": episode.series.slug, "name": episode.series.name},
            "episode": {"id": episode.id, "slug": episode.slug, "title": episode.title, "resolution": episode.effective_resolution, "fps": episode.effective_fps},
            "shot_count": len(shots),
            "shot_notes": notes,
            "qa": {"passed": qa_report.passed, "errors": qa_report.error_count, "warnings": qa_report.warning_count},
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        readme = destination / "README_IMPORT.txt"
        readme.write_text(
            "VIDEO GENSYSTEM — DAVINCI RESOLVE IMPORT\n\n"
            "1. Tạo project mới và đặt timeline resolution/FPS theo project_manifest.json.\n"
            "2. Import các folder audio, images, clips và subtitles vào Media Pool.\n"
            "3. Mở shot_manifest.csv, sort theo order_index; đặt motion_path nếu có, nếu không dùng image_path.\n"
            "4. Đặt audio_path cùng shot lên timeline và trim theo effective_duration_sec.\n"
            "5. Đối chiếu shot_id trên clip/audio trước khi dựng tiếp.\n"
            "6. Đọc qa/report.html tại episode root; QA nội dung, consistency, flicker, nhịp, music/SFX vẫn phải làm thủ công.\n\n"
            "CSV có đúng 16 cột dựng timeline. Notes nằm trong project_manifest.json để giải quyết chênh lệch 16/17 trường của đặc tả.\n",
            encoding="utf-8",
        )
    except Exception:
        (destination / "EXPORT_INCOMPLETE.txt").write_text("Export failed before completion.", encoding="utf-8")
        raise
    return ExportResult(destination, manifest, project_manifest, readme, count, len(shots), qa_report)
