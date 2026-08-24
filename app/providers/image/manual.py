from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.providers.image.base import ImageProvider, ProviderCost, ProviderError, copy_png_atomic, output_path


class ManualImageProvider(ImageProvider):
    name = "manual"

    def generate(
        self,
        prompt: str,
        reference_images: Sequence[Path],
        config: Mapping[str, Any],
    ) -> Path:
        del prompt, reference_images
        source = config.get("source_path")
        if not isinstance(source, str) or not source.strip():
            raise ProviderError("Manual provider requires source_path")
        return copy_png_atomic(Path(source), output_path(config))

    def cost(self, config: Mapping[str, Any]) -> ProviderCost:
        configured = super().cost(config)
        return ProviderCost(
            usd=0.0 if configured.usd is None else configured.usd,
            credit_amount=configured.credit_amount,
            credit_type=configured.credit_type,
            is_estimated=configured.is_estimated,
        )
