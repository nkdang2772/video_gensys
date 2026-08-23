from __future__ import annotations

import argparse

from app.db import SessionLocal
from app.services.errors import DomainError
from app.services.series import create_series


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Video GenSystem command line interface")
    resources = parser.add_subparsers(dest="resource", required=True)
    series_parser = resources.add_parser("series", help="Manage series")
    series_commands = series_parser.add_subparsers(dest="action", required=True)

    create_parser = series_commands.add_parser("create", help="Create a series")
    create_parser.add_argument("--name", required=True)
    create_parser.add_argument("--slug")
    create_parser.add_argument("--description")
    create_parser.add_argument("--resolution", default="1920x1080")
    create_parser.add_argument("--fps", type=float, default=30.0)
    create_parser.add_argument("--aspect-ratio", default="16:9")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.resource == "series" and args.action == "create":
            with SessionLocal.begin() as session:
                series = create_series(
                    session,
                    name=args.name,
                    slug=args.slug,
                    description=args.description,
                    default_resolution=args.resolution,
                    default_fps=args.fps,
                    default_aspect_ratio=args.aspect_ratio,
                )
                series_id, slug = series.id, series.slug
            print(f"Created series id={series_id} slug={slug}")
            return 0
    except (DomainError, ValueError) as exc:
        parser.error(str(exc))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

