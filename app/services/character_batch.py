from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence


def compute_batch_key(characters_list: Sequence[str | None]) -> str:
    if isinstance(characters_list, (str, bytes)) or not isinstance(characters_list, Sequence):
        raise ValueError("characters_list must be a sequence")
    characters = list(characters_list)
    if any(character is not None and (not isinstance(character, str) or not character) for character in characters):
        raise ValueError("Character IDs must be non-empty strings or null")
    if len(characters) != len(set(characters)):
        raise ValueError("characters_list may not contain duplicate IDs")
    canonical = sorted(characters, key=lambda value: (value is not None, value or ""))
    serialized = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

