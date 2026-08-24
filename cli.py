from __future__ import annotations

import argparse

from app.db import SessionLocal
from app.services.errors import DomainError
from app.services.reference import add_version, create_reference, list_versions
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

    reference_parser = resources.add_parser("reference", help="Manage references")
    reference_commands = reference_parser.add_subparsers(dest="action", required=True)
    reference_create = reference_commands.add_parser("create", help="Create a reference")
    reference_create.add_argument("--name", required=True)
    reference_create.add_argument("--slug")
    reference_create.add_argument(
        "--type", required=True, choices=["character", "style", "location", "prop", "map"]
    )
    reference_create.add_argument(
        "--scope",
        default="series_specific",
        choices=["series_specific", "shared_across_series"],
    )
    reference_create.add_argument("--series-id", type=int)

    reference_add = reference_commands.add_parser("add-version", help="Add an immutable version")
    reference_add.add_argument("--reference-id", type=int, required=True)
    reference_add.add_argument("--file", required=True)
    reference_add.add_argument("--library-root", default="library")

    reference_list = reference_commands.add_parser("list-versions", help="List reference versions")
    reference_list.add_argument("--reference-id", type=int, required=True)
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
        if args.resource == "reference" and args.action == "create":
            with SessionLocal.begin() as session:
                reference = create_reference(
                    session,
                    name=args.name,
                    slug=args.slug,
                    reference_type=args.type,
                    scope=args.scope,
                    owning_series_id=args.series_id,
                )
                reference_id, slug = reference.id, reference.slug
            print(f"Created reference id={reference_id} slug={slug}")
            return 0
        if args.resource == "reference" and args.action == "add-version":
            with SessionLocal() as session:
                version = add_version(
                    session,
                    reference_id=args.reference_id,
                    source_path=args.file,
                    library_root=args.library_root,
                )
                version_id, number = version.id, version.version
            print(f"Created reference_version id={version_id} version={number}")
            return 0
        if args.resource == "reference" and args.action == "list-versions":
            with SessionLocal() as session:
                versions = list_versions(session, args.reference_id)
                rows = [(version.id, version.version, version.file_path) for version in versions]
            for version_id, number, file_path in rows:
                print(f"id={version_id} version={number} file={file_path}")
            return 0
    except (DomainError, ValueError) as exc:
        parser.error(str(exc))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
