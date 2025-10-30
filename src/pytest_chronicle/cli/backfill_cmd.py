from __future__ import annotations

import argparse
import asyncio
from typing import Sequence

from pytest_chronicle.backfill import DEFAULT_BACKFILL_GLOBS, backfill, files_from_globs


def configure_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "backfill",
        help="Ingest historical summary.json artifacts into the tracking database.",
    )
    parser.add_argument(
        "--glob",
        dest="globs",
        action="append",
        default=None,
        help=f"Glob pattern(s) to locate summary artifacts (defaults to {DEFAULT_BACKFILL_GLOBS!r}).",
    )
    parser.add_argument("--database-url", help="Override database URL for ingestion.")
    parser.add_argument("--dry-run", action="store_true", help="List matching files without ingesting them.")
    return parser


def run(args: argparse.Namespace) -> int:
    patterns: Sequence[str] = args.globs or DEFAULT_BACKFILL_GLOBS
    files = files_from_globs(patterns)
    if not files:
        print("No matching summary.json files found.")
        return 0
    print(f"Found {len(files)} file(s).")
    if args.dry_run:
        for path in files:
            print(path)
        return 0

    try:
        outcome = asyncio.run(backfill(files, args.database_url))
    except KeyboardInterrupt:  # pragma: no cover - direct CLI usage
        return 130

    for path in outcome.ingested:
        print(f"Ingested: {path}")
    for path, error in outcome.failed:
        print(f"Failed to ingest {path}: {error}")

    return 0 if not outcome.failed else 1
