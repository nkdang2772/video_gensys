from __future__ import annotations

import argparse

from app import __version__


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app")
    parser.add_argument("--version", action="version", version=__version__)
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

