from __future__ import annotations

import argparse
from pathlib import Path

from sqlmodel import SQLModel, Session, create_engine, select  # type: ignore

from pytest_chronicle.models import TestCase, TestRun


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the pytest-chronicle database to a standalone SQLite file.",
    )
    parser.add_argument("--database-url", required=True, help="Source database URL (asyncpg/aiosqlite URLs supported).")
    parser.add_argument("--out", required=True, help="Destination SQLite path (will be created if missing).")
    return parser.parse_args(argv)


def normalize_sync_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    return url


def export_database(source_url: str, destination: Path) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    src_engine = create_engine(normalize_sync_url(source_url))
    dst_engine = create_engine(f"sqlite:///{destination}")
    SQLModel.metadata.create_all(dst_engine)

    exported = 0
    try:
        with Session(src_engine) as s_src, Session(dst_engine) as s_dst:
            runs = list(s_src.exec(select(TestRun)).all())
            for run in runs:
                s_dst.merge(TestRun(**run.model_dump(exclude_none=True)))
            s_dst.commit()
            exported = len(runs)

            for run in runs:
                cases = s_src.exec(select(TestCase).where(TestCase.run_id == run.id))
                for case in cases:
                    s_dst.merge(TestCase(**case.model_dump(exclude_none=True)))
                s_dst.commit()
    finally:
        src_engine.dispose()
        dst_engine.dispose()
    return exported


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    count = export_database(args.database_url, Path(args.out))
    print(f"Exported {count} runs to {args.out}")
    return 0


__all__ = ["export_database", "main", "normalize_sync_url", "parse_args"]
