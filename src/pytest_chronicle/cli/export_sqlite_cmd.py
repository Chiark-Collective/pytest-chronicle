from __future__ import annotations

import argparse
from pathlib import Path

from pytest_chronicle.export_sqlite import export_database


def configure_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "export-sqlite",
        help="Export the tracking database into a standalone SQLite file.",
    )
    parser.add_argument("--database-url", required=True, help="Source database URL.")
    parser.add_argument("--out", required=True, help="Destination SQLite path.")
    return parser


def run(args: argparse.Namespace) -> int:
    destination = Path(args.out)
    count = export_database(args.database_url, destination)
    print(f"Exported {count} runs to {destination}")
    return 0
