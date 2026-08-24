from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.motion.kenburns import render_kenburns
from app.providers.video.base import VideoProvider

SpriteRenderer = Callable[[Path, str, Mapping[str, Any]], Path]


@dataclass(frozen=True, slots=True)
class FallbackResult:
    output_path: Path
    method: str
    generative_attempts: int
    errors: tuple[str, ...]


def render_with_fallback(
    provider: VideoProvider,
    source_image: str | Path,
    prompt: str,
    output_path: str | Path,
    provider_config: Mapping[str, Any],
    *,
    sprite_renderer: SpriteRenderer | None = None,
    max_generative_attempts: int = 3,
    kenburns_config: Mapping[str, Any] | None = None,
) -> FallbackResult:
    if max_generative_attempts < 1:
        raise ValueError("max_generative_attempts must be at least one")
    source = Path(source_image).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    if destination.exists():
        raise ValueError(f"Motion fallback output already exists: {destination}")
    errors: list[str] = []
    for attempt in range(1, max_generative_attempts + 1):
        destination.unlink(missing_ok=True)
        config = dict(provider_config)
        config["output_path"] = str(destination)
        try:
            generated = provider.generate(source, prompt, config)
            if not generated.is_file():
                raise RuntimeError("provider returned a missing video")
            return FallbackResult(generated, provider.name, attempt, tuple(errors))
        except Exception as exc:
            destination.unlink(missing_ok=True)
            errors.append(f"{provider.name} attempt {attempt}: {type(exc).__name__}: {exc}")
    if sprite_renderer is not None:
        try:
            sprite_config = dict(provider_config)
            sprite_config["output_path"] = str(destination)
            generated = sprite_renderer(source, prompt, sprite_config)
            if not generated.is_file():
                raise RuntimeError("sprite renderer returned a missing video")
            return FallbackResult(generated, "sprite_local", max_generative_attempts, tuple(errors))
        except Exception as exc:
            destination.unlink(missing_ok=True)
            errors.append(f"sprite_local: {type(exc).__name__}: {exc}")
    else:
        errors.append("sprite_local: unavailable")
    config = dict(kenburns_config or {})
    duration = float(config.pop("duration", provider_config.get("fallback_duration_sec", 5.0)))
    generated = render_kenburns(
        source,
        duration,
        str(config.pop("direction", "zoom_in")),
        float(config.pop("zoom_start", 1.0)),
        float(config.pop("zoom_end", 1.04)),
        output_path=destination,
        **config,
    )
    return FallbackResult(generated, "internal_kenburns", max_generative_attempts, tuple(errors))
