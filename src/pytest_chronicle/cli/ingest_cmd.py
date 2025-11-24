from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from pytest_chronicle.config import get_default_config
from pytest_chronicle.ingest import ingest as ingest_async, default_database_url


def configure_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "ingest",
        help="Ingest a pytest summary or JSONL file into the configured database.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--summary", help="Path to summary.json produced by junit_to_summary.py")
    group.add_argument("--jsonl", help="Path to JSONL produced by the pytest results plugin")
    parser.add_argument("--database-url", help="Override database URL (otherwise env/default detection is used)")
    parser.add_argument("--project", help="Logical project name to store with the run")
    parser.add_argument("--label", "--labels", dest="labels", help="Comma-separated labels/tags to store with the run.")
    parser.add_argument("--suite", help="(Deprecated) suite label; prefer --label/--labels.")
    parser.add_argument("--run-id", help="Explicit run ID (UUID generated when omitted)")
    parser.add_argument("--run-key", help="Custom idempotency key (defaults to commit/project/suite hash)")
    parser.add_argument("--print-id", action="store_true", help="Print the run_id on success")
    return parser


async def _execute(args: argparse.Namespace) -> str:
    defaults = get_default_config()
    database_url = (args.database_url or default_database_url()).strip()
    summary_path = args.summary or args.jsonl
    assert summary_path, "Either --summary or --jsonl must be provided"
    labels = args.labels or args.suite
    if labels:
        labels = ",".join([p.strip() for p in labels.split(",") if p.strip()])
    return await ingest_async(
        summary_path=Path(summary_path),
        database_url=database_url,
        project=args.project or defaults.project,
        suite=labels or defaults.suite,
        run_id=args.run_id,
        run_key=args.run_key,
        print_id=args.print_id,
        pytest_args=None,
    )


def run(args: argparse.Namespace) -> int:
    try:
        asyncio.run(_execute(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # pragma: no cover - thin wrapper
        print(f"Error ingesting test results: {exc}")
        return 1
    return 0
