from __future__ import annotations

import hashlib
import math
import os
import shutil
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ProviderError(RuntimeError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderCost:
    usd: float | None = None
    credit_amount: float | None = None
    credit_type: str | None = None
    is_estimated: bool = False


class ImageProvider(ABC):
    name: str

    @abstractmethod
    def generate(
        self,
        prompt: str,
        reference_images: Sequence[Path],
        config: Mapping[str, Any],
    ) -> Path:
        """Generate one PNG and return its absolute output path."""

    def cost(self, config: Mapping[str, Any]) -> ProviderCost:
        def optional_cost(field: str) -> float | None:
            value = config.get(field)
            if value is None:
                return None
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ProviderError(f"{field} must be a finite non-negative number") from exc
            if not math.isfinite(number) or number < 0:
                raise ProviderError(f"{field} must be a finite non-negative number")
            return number

        usd = optional_cost("cost_usd")
        credit_amount = optional_cost("cost_credit_amount")
        credit_type = config.get("cost_credit_type")
        if credit_type not in {None, "veo", "imagen", "other"}:
            raise ProviderError(f"Unsupported credit type: {credit_type}")
        return ProviderCost(
            usd=usd,
            credit_amount=credit_amount,
            credit_type=credit_type,
            is_estimated=bool(config.get("cost_is_estimated", usd is not None)),
        )


def output_path(config: Mapping[str, Any]) -> Path:
    raw = config.get("output_path")
    if not isinstance(raw, str) or not raw.strip():
        raise ProviderError("Provider config requires output_path")
    destination = Path(raw).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.suffix.lower() != ".png":
        raise ProviderError("Provider output_path must use the .png extension")
    return destination


def validate_png_bytes(data: bytes) -> None:
    if len(data) < 24 or not data.startswith(PNG_SIGNATURE) or data[12:16] != b"IHDR":
        raise ProviderError("Provider output is not a valid PNG")


def write_png_atomic(destination: Path, data: bytes) -> Path:
    validate_png_bytes(data)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    if destination.exists():
        raise ProviderError(f"Provider output already exists: {destination}")
    try:
        with temporary.open("xb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def copy_png_atomic(source: Path, destination: Path) -> Path:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise ProviderError(f"Manual image does not exist: {source}")
    validate_png_bytes(source.read_bytes())
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    if destination.exists():
        raise ProviderError(f"Provider output already exists: {destination}")
    try:
        shutil.copy2(source, temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def png_metadata(path: Path) -> tuple[int, int, int, str]:
    data = path.read_bytes()
    validate_png_bytes(data)
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return width, height, len(data), hashlib.sha256(data).hexdigest()
