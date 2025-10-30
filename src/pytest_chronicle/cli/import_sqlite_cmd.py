from __future__ import annotations

import argparse
from pathlib import Path

from pytest_chronicle.import_sqlite import import_database


def configure_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "import-sqlite",
        help="Import a pytest-chronicle SQLite export into the target database.",
    )
    parser.add_argument("--sqlite", required=True, help="Path to the exported SQLite file.")
    parser.add_argument("--database-url", required=True, help="Destination database URL.")
    return parser


def run(args: argparse.Namespace) -> int:
    count = import_database(Path(args.sqlite), args.database_url)
    print(f"Imported {count} runs from {args.sqlite}")
    return 0
