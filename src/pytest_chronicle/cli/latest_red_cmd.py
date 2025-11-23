from __future__ import annotations

import argparse
import sys
from typing import Any, Dict

from sqlalchemy import create_engine, text  # type: ignore

from pytest_chronicle.config import ensure_sqlite_parent, resolve_database_url
from pytest_chronicle.ingest import default_database_url


def configure_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "latest-red",
        help="List tests whose latest recorded status is red (failed/error).",
    )
    parser.add_argument("--mode", choices=("per-test", "latest-run"), default="per-test", help="Selection strategy for failures.")
    parser.add_argument("--project-like", default="packages/survi%", help="SQL LIKE pattern for project column.")
    parser.add_argument("--suite", help="Optional suite filter.")
    parser.add_argument("--branch", help="Optional branch filter.")
    parser.add_argument("--database-url", help="Override database URL.")
    parser.add_argument("--print-sql", action="store_true", help="Print the executed SQL to stderr.")
    return parser


def _build_filters(args: argparse.Namespace) -> Dict[str, Any]:
    filters: Dict[str, Any] = {"project_like": args.project_like}
    if args.suite:
        filters["suite"] = args.suite
    if args.branch:
        filters["branch"] = args.branch
    return filters


def _build_sql(args: argparse.Namespace, dialect: str) -> str:
    filters = ["project LIKE :project_like"]
    if args.suite:
        filters.append("suite = :suite")
    if args.branch:
        filters.append("branch = :branch")
    where_with_alias = " AND ".join(f"tr.{f}" for f in filters)
    where_no_alias = " AND ".join(filters)

    if args.mode == "per-test":
        return f"""
        WITH ranked AS (
            SELECT
                tc.nodeid,
                tc.status,
                COALESCE(tc.message, '') AS message,
                tr.created_at,
                tr.id AS run_id,
                tr.suite,
                tr.branch,
                tr.head_sha,
                ROW_NUMBER() OVER (PARTITION BY tc.nodeid ORDER BY tr.created_at DESC) AS rn
            FROM test_cases tc
            JOIN test_runs tr ON tr.id = tc.run_id
            WHERE {where_with_alias}
        )
        SELECT nodeid
        FROM ranked
        WHERE rn = 1 AND status IN ('failed', 'error')
        ORDER BY created_at DESC;
        """

    return f"""
    WITH latest_run AS (
        SELECT id
        FROM test_runs
        WHERE {where_no_alias}
        ORDER BY created_at DESC
        LIMIT 1
    )
    SELECT tc.nodeid
    FROM test_cases tc
    JOIN latest_run lr ON lr.id = tc.run_id
    WHERE tc.status IN ('failed','error')
    ORDER BY tc.nodeid ASC;
    """


def _sync_url(db_url: str) -> str:
    if db_url.startswith("sqlite+aiosqlite://"):
        return db_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    if db_url.startswith("postgresql+asyncpg://"):
        return db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    return db_url


def run(args: argparse.Namespace) -> int:
    db_url = args.database_url or resolve_database_url() or default_database_url()
    ensure_sqlite_parent(db_url)
    engine = create_engine(_sync_url(db_url))
    sql = text(_build_sql(args, engine.url.get_dialect().name))
    if args.print_sql:
        print("-- Executing SQL:", file=sys.stderr)
        print(sql.text, file=sys.stderr)
    params = _build_filters(args)
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, params)
            for row in rows:
                print(row[0])
    finally:
        engine.dispose()
    return 0
