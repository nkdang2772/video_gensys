from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class VideoProviderError(RuntimeError):
    pass


class VideoProviderTimeoutError(VideoProviderError):
    pass


@dataclass(frozen=True, slots=True)
class VideoProviderCost:
    usd: float | None = None
    credit_amount: float | None = None
    credit_type: str | None = None
    is_estimated: bool = False


class VideoProvider(ABC):
    name: str

    @abstractmethod
    def generate(
        self,
        source_image: Path,
        prompt: str,
        config: Mapping[str, Any],
    ) -> Path:
        """Generate one MP4 and return its absolute path."""

    def cost(self, config: Mapping[str, Any]) -> VideoProviderCost:
        usd = config.get("cost_usd")
        credits = config.get("cost_credit_amount")
        credit_type = config.get("cost_credit_type")
        if usd is not None and float(usd) < 0:
            raise VideoProviderError("cost_usd cannot be negative")
        if credits is not None and float(credits) < 0:
            raise VideoProviderError("cost_credit_amount cannot be negative")
        if credit_type not in {None, "veo", "other"}:
            raise VideoProviderError(f"Unsupported video credit type: {credit_type}")
        return VideoProviderCost(
            usd=float(usd) if usd is not None else None,
            credit_amount=float(credits) if credits is not None else None,
            credit_type=credit_type,
            is_estimated=bool(config.get("cost_is_estimated", usd is not None)),
        )


def video_output_path(config: Mapping[str, Any]) -> Path:
    raw = config.get("output_path")
    if not isinstance(raw, str) or not raw.strip():
        raise VideoProviderError("Video provider config requires output_path")
    destination = Path(raw).expanduser().resolve()
    if destination.suffix.lower() != ".mp4":
        raise VideoProviderError("Video provider output_path must use the .mp4 extension")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def validate_mp4_bytes(data: bytes) -> None:
    if len(data) < 12 or b"ftyp" not in data[:64]:
        raise VideoProviderError("Provider output is not a valid MP4 container")


def validate_mp4_file(path: Path) -> None:
    if not path.is_file():
        raise VideoProviderError(f"Provider output is missing: {path}")
    with path.open("rb") as source:
        validate_mp4_bytes(source.read(64))


def write_mp4_atomic(destination: Path, data: bytes) -> Path:
    validate_mp4_bytes(data)
    if destination.exists():
        raise VideoProviderError(f"Video provider output already exists: {destination}")
    temporary = destination.with_name(f".{destination.stem}.{os.getpid()}.tmp.mp4")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("xb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def validate_source_image(source_image: str | Path) -> Path:
    source = Path(source_image).expanduser().resolve()
    if not source.is_file():
        raise VideoProviderError(f"Source image does not exist: {source}")
    return source
