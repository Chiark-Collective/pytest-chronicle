from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import text  # type: ignore
from sqlmodel import SQLModel, Session, create_engine, select  # type: ignore

from pytest_chronicle.models import TestCase, TestRun


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a pytest-chronicle SQLite snapshot into a destination database.",
    )
    parser.add_argument("--sqlite", required=True, help="Path to the exported SQLite file.")
    parser.add_argument("--database-url", required=True, help="Destination database URL (asyncpg/aiosqlite URLs supported).")
    return parser.parse_args(argv)


def normalize_sync_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    return url


def import_database(sqlite_path: Path, destination_url: str) -> int:
    src_engine = create_engine(f"sqlite:///{sqlite_path}")
    dst_engine = create_engine(normalize_sync_url(destination_url))
    SQLModel.metadata.create_all(dst_engine)

    imported = 0
    try:
        with Session(src_engine) as s_src, Session(dst_engine) as s_dst:
            runs = list(s_src.exec(select(TestRun)).all())
            for run in runs:
                existing = s_dst.exec(select(TestRun).where(TestRun.run_key == run.run_key)).first()
                if existing:
                    continue
                s_dst.add(TestRun(**run.model_dump(exclude_none=True)))
                imported += 1
            s_dst.commit()

            for run in runs:
                s_dst.exec(text("DELETE FROM test_cases WHERE run_id = :rid"), params={"rid": run.id})
                cases = s_src.exec(select(TestCase).where(TestCase.run_id == run.id))
                for case in cases:
                    s_dst.add(TestCase(**case.model_dump(exclude_none=True)))
                s_dst.commit()
    finally:
        src_engine.dispose()
        dst_engine.dispose()
    return imported


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    count = import_database(Path(args.sqlite), args.database_url)
    print(f"Imported {count} runs from {args.sqlite}")
    return 0


__all__ = ["import_database", "main", "normalize_sync_url", "parse_args"]
