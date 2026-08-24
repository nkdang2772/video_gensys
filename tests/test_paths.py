from pathlib import Path
from types import SimpleNamespace

import pytest

from app.paths import resolve, to_relative


def test_resolve_valid_asset_path(tmp_path: Path) -> None:
    episode = SimpleNamespace(root_path=str(tmp_path))
    assert resolve(episode, "images/s001.png") == (tmp_path / "images" / "s001.png").resolve()


@pytest.mark.parametrize(
    "unsafe",
    ["../../etc/passwd", "..\\..\\Windows\\win.ini", "C:\\Windows\\win.ini", "C:Windows\\win.ini"],
)
def test_resolve_rejects_path_traversal(tmp_path: Path, unsafe: str) -> None:
    episode = SimpleNamespace(root_path=str(tmp_path))
    with pytest.raises(ValueError, match="episode root"):
        resolve(episode, unsafe)


def test_to_relative_normalizes_separator(tmp_path: Path) -> None:
    episode = SimpleNamespace(root_path=str(tmp_path))
    absolute = tmp_path / "images" / "s001.png"
    assert to_relative(episode, absolute) == "images/s001.png"


def test_resolve_and_to_relative_round_trip(tmp_path: Path) -> None:
    episode = SimpleNamespace(root_path=str(tmp_path))
    relative = "images/generated/s001.png"
    assert to_relative(episode, resolve(episode, relative)) == relative


def test_to_relative_rejects_outside_path(tmp_path: Path) -> None:
    episode = SimpleNamespace(root_path=str(tmp_path / "episode"))
    with pytest.raises(ValueError, match="escapes episode root"):
        to_relative(episode, tmp_path / "outside.png")


def test_to_relative_rejects_relative_input(tmp_path: Path) -> None:
    episode = SimpleNamespace(root_path=str(tmp_path))
    with pytest.raises(ValueError, match="must be absolute"):
        to_relative(episode, "images/s001.png")
