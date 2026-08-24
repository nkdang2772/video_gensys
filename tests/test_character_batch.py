import hashlib
import json

import pytest

from app.services.character_batch import compute_batch_key


def test_character_order_does_not_change_batch_key() -> None:
    first = compute_batch_key(["sidekick", "tao_thao"])
    second = compute_batch_key(["tao_thao", "sidekick"])
    assert first == second
    canonical = json.dumps(["sidekick", "tao_thao"], sort_keys=True)
    assert first == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_empty_list_and_null_list_have_different_keys() -> None:
    assert compute_batch_key([]) != compute_batch_key([None])


def test_null_and_ids_use_canonical_order_without_mutating_input() -> None:
    characters = ["tao_thao", None, "sidekick"]
    original = list(characters)

    key = compute_batch_key(characters)

    canonical = json.dumps([None, "sidekick", "tao_thao"], sort_keys=True)
    assert key == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert characters == original


def test_duplicate_character_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        compute_batch_key(["hero", "hero"])
