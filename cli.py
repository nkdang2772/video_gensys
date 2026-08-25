from __future__ import annotations

import argparse
from pathlib import Path

from app.db import SessionLocal
from app.services.errors import DomainError
from app.services.reference import add_version, create_reference, list_versions
from app.services.series import create_series
from app.services.visual_setup import prepare_visual_episode
from app.providers.image import GoogleFlowImageProvider, ProviderError
from app.services.visual_reference import generate_reference_version


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
    reference_flow = reference_commands.add_parser(
        "generate-flow", help="Generate and store an immutable Google Flow version"
    )
    reference_flow.add_argument("--reference-id", type=int, required=True)
    reference_flow.add_argument("--library-root", default="library")
    reference_flow.add_argument("--downloads-root")
    reference_flow.add_argument("--bridge-port", type=int, default=8765)
    reference_flow.add_argument("--timeout", type=float, default=900.0)

    visual_parser = resources.add_parser("visual", help="Prepare a visual-first episode")
    visual_commands = visual_parser.add_subparsers(dest="action", required=True)
    visual_setup = visual_commands.add_parser("setup", help="Import script and prompt catalogs")
    visual_setup.add_argument("--series-name", required=True)
    visual_setup.add_argument("--episode-title", required=True)
    visual_setup.add_argument("--episode-number", type=int, default=1)
    visual_setup.add_argument("--library-root", default="library")
    visual_setup.add_argument("--script", required=True)
    visual_setup.add_argument("--character-prompts", required=True)
    visual_setup.add_argument("--background-prompts", required=True)
    visual_setup.add_argument("--planned-duration", type=float, default=4.0)
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
        if args.resource == "reference" and args.action == "generate-flow":
            config = {"bridge_port": args.bridge_port, "timeout_sec": args.timeout}
            if args.downloads_root:
                config["downloads_root"] = args.downloads_root
            with SessionLocal() as session:
                version = generate_reference_version(
                    session,
                    reference_id=args.reference_id,
                    provider=GoogleFlowImageProvider(),
                    library_root=args.library_root,
                    config=config,
                )
                version_id, number, file_path = version.id, version.version, version.file_path
            print(f"Created reference_version id={version_id} version={number} file={file_path}")
            return 0
        if args.resource == "visual" and args.action == "setup":
            result = prepare_visual_episode(
                SessionLocal,
                series_name=args.series_name,
                episode_title=args.episode_title,
                episode_number=args.episode_number,
                library_root=args.library_root,
                script_path=args.script,
                character_prompts_path=args.character_prompts,
                background_prompts_path=args.background_prompts,
                planned_duration_sec=args.planned_duration,
            )
            print(
                f"Prepared series_id={result.series_id} episode_id={result.episode_id} "
                f"references={result.reference_count} shots={result.shot_count} "
                f"character_mapped={result.character_mapped} "
                f"location_mapped={result.location_mapped} "
                f"root={result.episode_root}"
            )
            return 0
    except (DomainError, ProviderError, ValueError) as exc:
        parser.error(str(exc))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
