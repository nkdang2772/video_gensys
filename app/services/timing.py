from __future__ import annotations

from app.models import Shot


def effective_shot_duration(shot: Shot, *, fallback: float = 3.0) -> float:
    """Prefer real voice timing, then the visual-first provisional duration."""
    audio = float(shot.audio_duration_sec or 0.0)
    if audio > 0:
        return audio + float(shot.head_padding_sec or 0.0) + float(shot.tail_padding_sec or 0.0)
    planned = float(shot.planned_duration_sec or 0.0)
    return planned if planned > 0 else fallback
