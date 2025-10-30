from __future__ import annotations

import argparse
import asyncio
import glob
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from pytest_chronicle.ingest import default_database_url, ingest as ingest_async

DEFAULT_BACKFILL_GLOBS = ["packages/survi/reports/*/summary.json"]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill the test results database from existing summary.json artifacts.",
    )
    parser.add_argument(
        "--glob",
        dest="globs",
        action="append",
        default=list(DEFAULT_BACKFILL_GLOBS),
        help="Glob pattern(s) to locate summary.json files. Defaults to Survi report locations.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "Destination database URL; defaults to pytest-chronicle resolution "
            "(PYTEST_RESULTS_DB_URL / TEST_RESULTS_DATABASE_URL / sqlite fallback)."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="List matched files without ingesting them.")
    return parser.parse_args(argv)


def files_from_globs(patterns: Iterable[str]) -> list[Path]:
    matches: set[Path] = set()
    for pattern in patterns:
        for match in glob.glob(pattern):
            matches.add(Path(match))
    return sorted(path for path in matches if path.exists())


@dataclass(slots=True)
class BackfillOutcome:
    ingested: list[Path]
    failed: list[tuple[Path, Exception]]


async def backfill(paths: Sequence[Path], database_url: str | None = None) -> BackfillOutcome:
    if not paths:
        return BackfillOutcome(ingested=[], failed=[])

    db_url = (database_url or default_database_url()).strip()
    successes: list[Path] = []
    failures: list[tuple[Path, Exception]] = []

    for path in paths:
        try:
            await ingest_async(
                summary_path=path,
                database_url=db_url,
                project=None,
                suite=None,
                run_id=None,
                run_key=None,
                print_id=False,
            )
            successes.append(path)
        except Exception as exc:  # pragma: no cover - surfaced via CLI messaging
            failures.append((path, exc))
    return BackfillOutcome(ingested=successes, failed=failures)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    files = files_from_globs(args.globs or DEFAULT_BACKFILL_GLOBS)
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
    except KeyboardInterrupt:  # pragma: no cover - direct CLI interaction
        return 130

    for path in outcome.ingested:
        print(f"Ingested: {path}")
    for path, error in outcome.failed:
        print(f"Failed to ingest {path}: {error}")

    return 0 if not outcome.failed else 1


__all__ = [
    "DEFAULT_BACKFILL_GLOBS",
    "BackfillOutcome",
    "files_from_globs",
    "backfill",
    "main",
    "parse_args",
]
