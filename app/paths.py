from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Protocol


class EpisodeWithRoot(Protocol):
    root_path: str


def _root(episode: EpisodeWithRoot) -> Path:
    return Path(episode.root_path).expanduser().resolve()


def _ensure_inside(root: Path, candidate: Path) -> Path:
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path escapes episode root: {candidate}") from exc
    return candidate


def resolve(episode: EpisodeWithRoot, relative_path: str | Path) -> Path:
    raw = str(relative_path)
    relative = PurePosixPath(raw.replace("\\", "/"))
    if relative.is_absolute() or Path(raw).is_absolute() or PureWindowsPath(raw).drive:
        raise ValueError("Asset path must be relative to the episode root")
    root = _root(episode)
    return _ensure_inside(root, (root / Path(*relative.parts)).resolve())


def to_relative(episode: EpisodeWithRoot, absolute_path: str | Path) -> str:
    root = _root(episode)
    candidate_input = Path(absolute_path).expanduser()
    if not candidate_input.is_absolute():
        raise ValueError("Asset path must be absolute before converting to an episode-relative path")
    candidate = candidate_input.resolve()
    relative = _ensure_inside(root, candidate).relative_to(root)
    return relative.as_posix()
