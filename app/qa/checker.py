from __future__ import annotations

import hashlib
import html
import json
import math
import tempfile
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.media.ffprobe import FFprobeError, probe_audio, probe_video
from app.media.ffmpeg import run_ffmpeg
from app.models import Asset, Episode, Job, Shot
from app.paths import resolve
from app.services.timing import effective_shot_duration


@dataclass(frozen=True, slots=True)
class QaIssue:
    severity: str
    code: str
    message: str
    shot_id: str | None = None
    asset_id: int | None = None


@dataclass(frozen=True, slots=True)
class QaReport:
    episode_id: int
    generated_at: str
    passed: bool
    shot_count: int
    error_count: int
    warning_count: int
    placeholder_shot_ids: tuple[str, ...]
    total_effective_audio_sec: float
    total_visual_timeline_sec: float
    issues: tuple[QaIssue, ...]
    json_path: Path | None = None
    html_path: Path | None = None


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _chosen(shot: Shot, kind: str) -> Asset | None:
    return next((item for item in shot.assets if item.asset_type == kind and item.is_chosen), None)


def _effective_duration(shot: Shot, *, require_audio: bool) -> float:
    if require_audio:
        return float(shot.audio_duration_sec or 0) + float(shot.head_padding_sec or 0) + float(shot.tail_padding_sec or 0)
    return effective_shot_duration(shot, fallback=0.0)


def _resolution(value: str) -> tuple[int, int] | None:
    try:
        width, height = value.lower().split("x", 1)
        parsed = int(width), int(height)
    except (AttributeError, TypeError, ValueError):
        return None
    return parsed if parsed[0] > 0 and parsed[1] > 0 else None


def _is_abnormal_still(path: Path) -> bool:
    with Image.open(path) as image:
        stat = ImageStat.Stat(image.convert("RGB").resize((64, 64)))
    mean = sum(stat.mean) / 3
    deviation = sum(stat.stddev) / 3
    return deviation < 2 and (mean < 3 or mean > 252)


def _video_frame(path: Path, timestamp: float, *, ffmpeg_path: str | Path | None) -> Path:
    handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    output = Path(handle.name)
    handle.close()
    output.unlink(missing_ok=True)
    try:
        run_ffmpeg(
            ["-y", "-ss", f"{max(0, timestamp):.6f}", "-i", str(path), "-frames:v", "1", str(output)],
            ffmpeg_path=ffmpeg_path,
            timeout_sec=60,
        )
        if not output.is_file():
            raise OSError("FFmpeg did not extract a QA frame")
        return output
    except Exception:
        output.unlink(missing_ok=True)
        raise


def _frame_distance(first: Path, last: Path) -> float:
    with Image.open(first) as a, Image.open(last) as b:
        difference = ImageChops.difference(a.convert("RGB").resize((64, 64)), b.convert("RGB").resize((64, 64)))
        return sum(ImageStat.Stat(difference).mean) / (3 * 255)


def _payload(report: QaReport) -> dict[str, object]:
    return {
        "episode_id": report.episode_id,
        "generated_at": report.generated_at,
        "passed": report.passed,
        "shot_count": report.shot_count,
        "error_count": report.error_count,
        "warning_count": report.warning_count,
        "placeholder_shot_ids": list(report.placeholder_shot_ids),
        "total_effective_audio_sec": report.total_effective_audio_sec,
        "total_visual_timeline_sec": report.total_visual_timeline_sec,
        "issues": [asdict(issue) for issue in report.issues],
        "manual_review_required": [
            "content and narration accuracy", "character consistency",
            "warp/flicker and motion continuity", "map accuracy",
            "editing rhythm, music and SFX", "loop seamlessness",
        ],
    }


def _write_reports(report: QaReport, folder: Path) -> tuple[Path, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    json_path, html_path = folder / "report.json", folder / "report.html"
    payload = _payload(report)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = "".join(
        f"<tr><td>{html.escape(i.severity)}</td><td>{html.escape(i.code)}</td>"
        f"<td>{html.escape(i.shot_id or '-')}</td><td>{html.escape(i.message)}</td></tr>"
        for i in report.issues
    ) or '<tr><td colspan="4">No automatic QA issues.</td></tr>'
    manual = "".join(f"<li>{html.escape(item)}</li>" for item in payload["manual_review_required"])
    html_path.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Episode QA report</title>
<style>body{{font-family:Arial,sans-serif;margin:2rem}}.pass{{color:#087830}}.fail{{color:#b00020}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccc;padding:.5rem;text-align:left}}th{{background:#eee}}</style></head>
<body><h1>Episode QA report</h1><p class="{'pass' if report.passed else 'fail'}"><strong>{'PASS' if report.passed else 'FAIL'}</strong> — {report.error_count} error(s), {report.warning_count} warning(s)</p>
<p>Generated: {html.escape(report.generated_at)} · Shots: {report.shot_count} · Effective audio: {report.total_effective_audio_sec:.3f}s · Visual timeline: {report.total_visual_timeline_sec:.3f}s</p>
<p>Placeholders: {html.escape(', '.join(report.placeholder_shot_ids) or 'none')}</p>
<table><thead><tr><th>Severity</th><th>Rule</th><th>Shot</th><th>Message</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Manual review still required</h2><ul>{manual}</ul></body></html>""", encoding="utf-8")
    return json_path, html_path


def run_asset_checks(
    session: Session,
    episode_id: int,
    *,
    ffmpeg_path: str | Path | None = None,
    ffprobe_path: str | Path | None = None,
    stale_timeout: timedelta = timedelta(minutes=30),
    write_report: bool = True,
    require_audio: bool = True,
) -> QaReport:
    episode = session.get(Episode, episode_id)
    if episode is None:
        raise ValueError(f"Episode not found: {episode_id}")
    shots = list(session.scalars(select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.order_index, Shot.id)))
    issues: list[QaIssue] = []
    lowered: set[str] = set()
    expected_resolution = _resolution(episode.effective_resolution)
    total_audio = total_visual = 0.0
    placeholders: list[str] = []

    for shot in shots:
        normalized = (shot.shot_id or "").strip().lower()
        if not normalized:
            issues.append(QaIssue("error", "missing_shot_id", "Shot ID is empty"))
        elif normalized in lowered:
            issues.append(QaIssue("error", "duplicate_shot_id", "Shot ID is duplicated ignoring case", shot.shot_id))
        lowered.add(normalized)
        audio, image, motion = _chosen(shot, "audio"), _chosen(shot, "image"), _chosen(shot, "video")
        effective = _effective_duration(shot, require_audio=require_audio)
        total_audio += effective
        if require_audio and (audio is None or effective <= 0):
            issues.append(QaIssue("error", "audio_duration", "Chosen audio and duration > 0 are required", shot.shot_id, audio.id if audio else None))
        elif not require_audio and effective <= 0:
            issues.append(QaIssue("error", "planned_duration", "Visual-first mode requires planned_duration_sec > 0", shot.shot_id))
        elif not require_audio and audio is None:
            issues.append(QaIssue("warning", "audio_deferred", "Voice is intentionally deferred; planned duration is used", shot.shot_id))
        visual = motion or image
        if visual is None:
            placeholders.append(shot.shot_id)
            issues.extend((
                QaIssue("error", "missing_visual", "No chosen image or motion; preview uses a red placeholder", shot.shot_id),
                QaIssue("warning", "placeholder", "Red placeholder is required for this shot", shot.shot_id),
            ))
            total_visual += effective

        for asset in [item for item in (audio, image, motion) if item is not None]:
            try:
                path = resolve(episode, asset.file_path)
            except ValueError as exc:
                issues.append(QaIssue("error", "unsafe_path", str(exc), shot.shot_id, asset.id))
                continue
            if not path.is_file():
                issues.append(QaIssue("error", "missing_file", f"Chosen file does not exist: {asset.file_path}", shot.shot_id, asset.id))
                continue
            if not asset.checksum:
                issues.append(QaIssue("error", "missing_checksum", "Chosen asset has no checksum", shot.shot_id, asset.id))
            elif _checksum(path).lower() != asset.checksum.lower():
                issues.append(QaIssue("error", "checksum_mismatch", "Chosen file checksum does not match the database", shot.shot_id, asset.id))
            try:
                if asset.asset_type == "audio":
                    probe_audio(path, ffprobe_path=ffprobe_path)
                elif asset.asset_type == "video":
                    metadata = probe_video(path, ffprobe_path=ffprobe_path)
                    if expected_resolution and (metadata.width, metadata.height) != expected_resolution:
                        issues.append(QaIssue("error", "video_resolution", f"Video is {metadata.width}x{metadata.height}; expected {expected_resolution[0]}x{expected_resolution[1]}", shot.shot_id, asset.id))
                    if not math.isclose(metadata.frame_rate, float(episode.effective_fps), abs_tol=0.05):
                        issues.append(QaIssue("error", "video_fps", f"Video is {metadata.frame_rate:g} FPS; expected {episode.effective_fps:g}", shot.shot_id, asset.id))
                    if metadata.codec not in {"h264", "hevc", "prores"}:
                        issues.append(QaIssue("error", "video_codec", f"Unsupported delivery codec: {metadata.codec}", shot.shot_id, asset.id))
                    sample = _video_frame(path, metadata.duration_sec / 2, ffmpeg_path=ffmpeg_path)
                    try:
                        if _is_abnormal_still(sample):
                            issues.append(QaIssue("error", "abnormal_frame", "Sampled motion frame is near-solid black or white", shot.shot_id, asset.id))
                    finally:
                        sample.unlink(missing_ok=True)
                elif asset.asset_type == "image":
                    with Image.open(path) as source:
                        source.verify()
                    if _is_abnormal_still(path):
                        issues.append(QaIssue("warning", "abnormal_frame", "Chosen image is near-solid black or white", shot.shot_id, asset.id))
            except (FFprobeError, OSError, ValueError, SyntaxError) as exc:
                issues.append(QaIssue("error", "unreadable_metadata", str(exc), shot.shot_id, asset.id))

        if motion is not None:
            duration = float(motion.duration_sec or 0)
            try:
                path = resolve(episode, motion.file_path)
                if path.is_file():
                    duration = probe_video(path, ffprobe_path=ffprobe_path).duration_sec
            except (ValueError, FFprobeError):
                pass
            total_visual += min(duration, effective) if effective > 0 else duration
            if duration + 0.1 < effective:
                if shot.motion_fill_policy not in {"extend", "split", "loop"}:
                    issues.append(QaIssue("error", "invalid_fill_policy", "Motion shorter than voice requires extend, split or explicit loop", shot.shot_id, motion.id))
                elif shot.motion_fill_policy == "extend":
                    issues.append(QaIssue("error", "extend_incomplete", "Final-frame Ken Burns fill is missing", shot.shot_id, motion.id))
            if shot.motion_fill_policy == "loop":
                first = last = None
                try:
                    path = resolve(episode, motion.file_path)
                    metadata = probe_video(path, ffprobe_path=ffprobe_path)
                    first = _video_frame(path, 0.0, ffmpeg_path=ffmpeg_path)
                    last = _video_frame(path, max(0, metadata.duration_sec - 0.1), ffmpeg_path=ffmpeg_path)
                    distance = _frame_distance(first, last)
                    message = f"Loop is explicit; first/last technical frame distance is {distance:.3f}; confirm seamlessness manually"
                    code = "loop_not_seamless" if distance > 0.15 else "loop_manual_review"
                    issues.append(QaIssue("warning", code, message, shot.shot_id, motion.id))
                except (OSError, RuntimeError, FFprobeError, ValueError) as exc:
                    issues.append(QaIssue("warning", "loop_check_failed", f"Could not compare loop boundary frames: {exc}", shot.shot_id, motion.id))
                finally:
                    if first is not None:
                        first.unlink(missing_ok=True)
                    if last is not None:
                        last.unlink(missing_ok=True)
        elif image is not None:
            total_visual += effective

    now = datetime.now(UTC)
    for job in session.scalars(select(Job).where(Job.episode_id == episode_id, Job.status.in_(("running", "failed")))):
        started = job.started_at if not job.started_at or job.started_at.tzinfo else job.started_at.replace(tzinfo=UTC)
        stale = job.status == "running" and started is not None and now - started > stale_timeout
        issues.append(QaIssue("error", "stale_job" if stale else f"{job.status}_job", f"Unresolved Job #{job.id}: {job.error_message or job.status}", job.shot.shot_id if job.shot else None))
    tolerance = max(0.1, total_audio * 0.01)
    if abs(total_visual - total_audio) > tolerance:
        issues.append(QaIssue("error", "total_timing", f"Visual timeline {total_visual:.3f}s differs from effective audio {total_audio:.3f}s"))
    errors = sum(item.severity == "error" for item in issues)
    warnings = sum(item.severity == "warning" for item in issues)
    report = QaReport(episode_id, datetime.now(UTC).isoformat(), errors == 0, len(shots), errors, warnings, tuple(placeholders), round(total_audio, 6), round(total_visual, 6), tuple(issues))
    if write_report:
        json_path, html_path = _write_reports(report, resolve(episode, "qa"))
        report = replace(report, json_path=json_path, html_path=html_path)
    return report
