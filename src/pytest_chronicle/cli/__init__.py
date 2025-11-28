"""CLI entry points for pytest-chronicle."""

from __future__ import annotations

import argparse
import sys

from . import (
    backfill_cmd,
    config_cmd,
    db_cmd,
    export_sqlite_cmd,
    import_sqlite_cmd,
    ingest_cmd,
    init_cmd,
    latest_red_cmd,
    query_cmd,
    run_cmd,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pytest-chronicle",
        description="pytest-chronicle: Track your pytest test history across runs.",
        epilog="""Quick start:
  pytest-chronicle init          # Initialize in current directory
  pytest                         # Run tests (auto-ingests results)
  pytest-chronicle query stats   # View test statistics

Common queries:
  query last-red    - Recent failures
  query errors      - Error details with tracebacks
  query timeline    - Visual test history
  query slowest     - Performance analysis
  query stats       - Failure rates and timing

GitHub: https://github.com/Chiark-Collective/pytest-chronicle
Docs:   https://pypi.org/project/pytest-chronicle/""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    ingest_cmd.configure_parser(subparsers)
    latest_red_cmd.configure_parser(subparsers)
    run_cmd.configure_parser(subparsers)
    backfill_cmd.configure_parser(subparsers)
    export_sqlite_cmd.configure_parser(subparsers)
    import_sqlite_cmd.configure_parser(subparsers)
    db_cmd.configure_parser(subparsers)
    query_cmd.configure_parser(subparsers)
    config_cmd.configure_parser(subparsers)
    init_cmd.configure_parser(subparsers)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help(sys.stderr)
        return 1

    if args.command == "ingest":
        return ingest_cmd.run(args)
    if args.command == "latest-red":
        return latest_red_cmd.run(args)
    if args.command == "run":
        return run_cmd.run(args)
    if args.command == "backfill":
        return backfill_cmd.run(args)
    if args.command == "export-sqlite":
        return export_sqlite_cmd.run(args)
    if args.command == "import-sqlite":
        return import_sqlite_cmd.run(args)
    if args.command == "db":
        return db_cmd.run(args)
    if args.command == "query":
        return query_cmd.run(args)
    if args.command == "config":
        return config_cmd.run(args)
    if args.command == "init":
        return init_cmd.run(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


__all__ = ["main"]
