from __future__ import annotations

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Episode, Scene, Shot
from app.parsers.common import ParsedShot
from app.paths import resolve
from app.services.character_batch import compute_batch_key
from app.services.errors import DomainError


class ScriptImportError(DomainError):
    pass


def import_parsed_script(
    session: Session,
    *,
    episode_id: int,
    parsed_shots: list[ParsedShot],
    source_name: str | None = None,
    source_bytes: bytes | None = None,
    planned_duration_sec: float = 4.0,
) -> list[Shot]:
    if session.in_transaction():
        raise ScriptImportError("import_parsed_script requires a Session without an active transaction")
    if not parsed_shots:
        raise ScriptImportError("Script contains no shots")
    shot_ids = [shot.shot_id.lower() for shot in parsed_shots]
    if len(shot_ids) != len(set(shot_ids)):
        raise ScriptImportError("Script contains duplicate shot_id values")
    if (source_name is None) != (source_bytes is None):
        raise ValueError("source_name and source_bytes must be provided together")
    if planned_duration_sec <= 0:
        raise ValueError("planned_duration_sec must be positive")

    stored_script: Path | None = None
    try:
        with session.begin():
            episode = session.get(Episode, episode_id)
            if episode is None:
                raise ScriptImportError(f"Episode not found: {episode_id}")
            existing_count = session.scalar(
                select(func.count()).select_from(Shot).where(Shot.episode_id == episode.id)
            )
            if existing_count:
                raise ScriptImportError("Episode already contains shots")

            if source_name is not None and source_bytes is not None:
                safe_name = Path(source_name).name
                if not safe_name or Path(safe_name).suffix.lower() not in {".txt", ".csv", ".json"}:
                    raise ScriptImportError("Script source name must be a safe TXT/CSV/JSON filename")
                stored_script = resolve(episode, f"script/{safe_name}")
                stored_script.parent.mkdir(parents=True, exist_ok=True)
                if stored_script.exists():
                    raise ScriptImportError(f"Script source already exists: {stored_script}")
                stored_script.write_bytes(source_bytes)

            scene_values: list[str] = []
            for parsed in parsed_shots:
                if parsed.scene is not None and parsed.scene not in scene_values:
                    scene_values.append(parsed.scene)
            scenes: dict[str, Scene] = {}
            for index, scene_value in enumerate(scene_values, start=1):
                scene = Scene(
                    episode=episode,
                    scene_number=index,
                    title=scene_value,
                    order_index=index,
                )
                session.add(scene)
                scenes[scene_value] = scene
            session.flush()

            imported: list[Shot] = []
            for index, parsed in enumerate(parsed_shots, start=1):
                shot = Shot(
                    episode=episode,
                    scene=scenes.get(parsed.scene) if parsed.scene is not None else None,
                    shot_id=parsed.shot_id,
                    order_index=index,
                    speaker=parsed.speaker,
                    voice_text=parsed.text,
                    visual_description=parsed.visual_description,
                    motion_intent=parsed.motion_intent,
                    motion_provider="none",
                    motion_fill_policy="extend",
                    characters_json=[],
                    character_batch_key=compute_batch_key([]),
                    planned_duration_sec=planned_duration_sec,
                    status="draft",
                )
                session.add(shot)
                imported.append(shot)
            session.flush()
        return imported
    except Exception as exc:
        if stored_script is not None and stored_script.exists():
            try:
                stored_script.unlink()
            except OSError as cleanup_error:
                raise ScriptImportError(
                    f"Script import failed and source cleanup also failed: {stored_script}"
                ) from cleanup_error
        if isinstance(exc, ScriptImportError):
            raise
        raise ScriptImportError(f"Could not import script: {exc}") from exc
