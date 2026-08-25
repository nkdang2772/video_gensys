from __future__ import annotations

import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Reference, ReferenceVersion
from app.providers.image.base import ImageProvider
from app.services.reference import add_version


def generate_reference_version(
    session: Session,
    *,
    reference_id: int,
    provider: ImageProvider,
    library_root: str | Path,
    config: dict | None = None,
) -> ReferenceVersion:
    reference = session.get(Reference, reference_id)
    if reference is None:
        raise ValueError(f"Reference not found: {reference_id}")
    prompt = (reference.generation_prompt or "").strip()
    if not prompt:
        raise ValueError(f"Reference {reference.slug!r} has no generation prompt")
    cost = provider.cost(config or {})
    with tempfile.TemporaryDirectory(prefix="video-gensystem-reference-") as temporary:
        output = Path(temporary) / f"{reference.slug}.png"
        provider_config = {**(config or {}), "output_path": str(output)}
        generated = provider.generate(prompt, (), provider_config)
        descriptor = {
            "source": "generated",
            "provider": provider.name,
            "prompt": prompt,
            "cost_usd": cost.usd,
            "cost_credit_amount": cost.credit_amount,
            "cost_credit_type": cost.credit_type,
            "cost_is_estimated": cost.is_estimated,
        }
        # add_version owns its transaction; discard the read-only autobegin first.
        session.rollback()
        return add_version(
            session,
            reference_id=reference_id,
            source_path=generated,
            library_root=library_root,
            descriptor_json=descriptor,
        )
