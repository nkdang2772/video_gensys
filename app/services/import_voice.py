from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.media.ffprobe import FFprobeError, probe_audio
from app.models import Asset, Episode, Shot
from app.paths import resolve, to_relative
from app.services.errors import DomainError

S_SHOT_PATTERN = re.compile(r"(?<![a-z0-9])(s\d+)(?!\d)", re.IGNORECASE)
SAFE_FILE_COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class VoiceImportError(DomainError):
    pass


@dataclass(frozen=True, slots=True)
class VoiceImportWarning:
    code: str
    message: str
    file_path: str | None = None
    shot_id: str | None = None


@dataclass(slots=True)
class VoiceImportReport:
    imported_assets: list[Asset] = field(default_factory=list)
    warnings: list[VoiceImportWarning] = field(default_factory=list)


def match_shot_id(filename: str, known_shot_ids: set[str]) -> str | None:
    normalized_ids = {shot_id.lower() for shot_id in known_shot_ids}
    stem = Path(filename).stem.lower()
    s_matches = {match.group(1).lower() for match in S_SHOT_PATTERN.finditer(stem)}
    known_matches = s_matches & normalized_ids
    if len(known_matches) == 1:
        return next(iter(known_matches))
    if len(known_matches) > 1:
        return None
    for shot_id in sorted(normalized_ids, key=len, reverse=True):
        if stem == shot_id or re.match(rf"^{re.escape(shot_id)}(?:[_\-. ]|$)", stem):
            return shot_id
    return None


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_voice_folder(
    session: Session,
    *,
    episode_id: int,
    folder: str | Path,
    ffprobe_path: str | Path | None = None,
) -> VoiceImportReport:
    if session.in_transaction():
        raise VoiceImportError("import_voice_folder requires a Session without an active transaction")
    source_folder = Path(folder).expanduser().resolve()
    if not source_folder.is_dir():
        raise VoiceImportError(f"Voice folder does not exist: {source_folder}")
    source_files = sorted(
        (path for path in source_folder.iterdir() if path.is_file() and path.suffix.lower() == ".wav"),
        key=lambda path: path.name.lower(),
    )

    report = VoiceImportReport()
    created_files: list[Path] = []
    successfully_linked: set[str] = set()
    claimed_shots: set[str] = set()
    try:
        with session.begin():
            episode = session.get(Episode, episode_id)
            if episode is None:
                raise VoiceImportError(f"Episode not found: {episode_id}")
            shots = list(
                session.scalars(
                    select(Shot).where(Shot.episode_id == episode.id).order_by(Shot.order_index)
                )
            )
            shots_by_id = {shot.shot_id.lower(): shot for shot in shots}
            if len(shots_by_id) != len(shots):
                raise VoiceImportError("Episode contains duplicate shot_id values ignoring case")
            unsafe_ids = [
                shot.shot_id
                for shot in shots
                if not SAFE_FILE_COMPONENT_PATTERN.fullmatch(shot.shot_id)
            ]
            if unsafe_ids:
                raise VoiceImportError(
                    f"Unsafe shot_id cannot be used in an asset filename: {unsafe_ids[0]!r}"
                )
            chosen_shot_ids = set(
                session.scalars(
                    select(Asset.shot_id).where(
                        Asset.episode_id == episode.id,
                        Asset.asset_type == "audio",
                        Asset.is_chosen.is_(True),
                        Asset.shot_id.is_not(None),
                    )
                )
            )
            successfully_linked.update(
                shot.shot_id.lower() for shot in shots if shot.id in chosen_shot_ids
            )
            destination_folder = resolve(episode, "audio/source")
            destination_folder.mkdir(parents=True, exist_ok=True)

            for source_file in source_files:
                matched_id = match_shot_id(source_file.name, set(shots_by_id))
                if matched_id is None:
                    report.warnings.append(
                        VoiceImportWarning(
                            code="unmatched_file",
                            message="WAV filename could not be linked to a known shot_id",
                            file_path=str(source_file),
                        )
                    )
                    continue
                if matched_id in claimed_shots:
                    report.warnings.append(
                        VoiceImportWarning(
                            code="duplicate_audio_for_shot",
                            message="More than one WAV matched the same shot; later file was skipped",
                            file_path=str(source_file),
                            shot_id=matched_id,
                        )
                    )
                    continue
                shot = shots_by_id[matched_id]
                try:
                    metadata = probe_audio(source_file, ffprobe_path=ffprobe_path)
                except FFprobeError as exc:
                    report.warnings.append(
                        VoiceImportWarning(
                            code="probe_failed",
                            message=str(exc),
                            file_path=str(source_file),
                            shot_id=matched_id,
                        )
                    )
                    continue
                claimed_shots.add(matched_id)

                latest_version = session.scalar(
                    select(func.max(Asset.version)).where(
                        Asset.shot_id == shot.id, Asset.asset_type == "audio"
                    )
                ) or 0
                version = latest_version + 1
                destination = destination_folder / (
                    f"{shot.shot_id}_audio_v{version:02d}_chosen{source_file.suffix.lower()}"
                )
                if destination.exists():
                    raise VoiceImportError(f"Destination file already exists: {destination}")
                shutil.copy2(source_file, destination)
                created_files.append(destination)

                chosen_assets = list(
                    session.scalars(
                        select(Asset).where(
                            Asset.shot_id == shot.id,
                            Asset.asset_type == "audio",
                            Asset.is_chosen.is_(True),
                        )
                    )
                )
                for chosen in chosen_assets:
                    chosen.is_chosen = False
                shot.audio_start_sec = 0.0
                shot.audio_end_sec = metadata.duration_sec
                shot.audio_duration_sec = metadata.duration_sec
                relative_path = to_relative(episode, destination)
                asset = Asset(
                    episode=episode,
                    shot=shot,
                    asset_type="audio",
                    version=version,
                    is_chosen=True,
                    provider="manual_import",
                    source_path=relative_path,
                    file_path=relative_path,
                    duration_sec=metadata.duration_sec,
                    codec=metadata.codec,
                    file_size=destination.stat().st_size,
                    checksum=_checksum(destination),
                )
                session.add(asset)
                session.flush()
                report.imported_assets.append(asset)
                successfully_linked.add(matched_id)

            for shot_id in sorted(set(shots_by_id) - successfully_linked):
                report.warnings.append(
                    VoiceImportWarning(
                        code="missing_audio_for_shot",
                        message="No usable WAV was imported for this shot",
                        shot_id=shot_id,
                    )
                )
        return report
    except Exception as exc:
        cleanup_failures: list[str] = []
        for created_file in reversed(created_files):
            try:
                created_file.unlink(missing_ok=True)
            except OSError as cleanup_error:
                cleanup_failures.append(f"{created_file}: {cleanup_error}")
        if cleanup_failures:
            raise VoiceImportError(
                "Voice import failed and copied-file cleanup also failed: "
                + "; ".join(cleanup_failures)
            ) from exc
        raise
