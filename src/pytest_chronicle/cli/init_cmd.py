from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from pytest_chronicle.config import (
    TrackerConfig,
    default_config_path,
    fallback_sqlite_url,
    get_default_config,
    load_repo_config,
    ensure_sqlite_parent,
    write_config,
)
from pytest_chronicle.ingest import ensure_schema


def _to_async_url(db_url: str) -> str:
    if db_url.startswith("postgresql://"):
        return db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if db_url.startswith("sqlite:///") and "+aiosqlite" not in db_url:
        return db_url.replace("sqlite:///", "sqlite+aiosqlite:///")
    return db_url


async def _create_schema(db_url: str) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine  # type: ignore

    engine = create_async_engine(_to_async_url(db_url), pool_pre_ping=True)
    await ensure_schema(engine)
    await engine.dispose()


def configure_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "init",
        help="Create a repo-local .pytest-chronicle.toml and an async SQLite database by default.",
    )
    parser.add_argument("--database-url", help="Database URL to persist (default: async SQLite under the repo).")
    parser.add_argument("--project", help="Default project name to store in runs.")
    parser.add_argument("--suite", help="Default suite name to store in runs.")
    parser.add_argument("--config-path", help="Where to write the config (default: repo/.pytest-chronicle.toml).")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing config file.")
    parser.add_argument(
        "--no-schema",
        action="store_true",
        help="Skip creating or updating the database schema (default is on for SQLite).",
    )
    parser.add_argument(
        "--apply-schema",
        action="store_true",
        help="Force schema creation even for non-SQLite URLs (requires drivers to be installed).",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    cwd = Path.cwd()
    cfg_path = Path(args.config_path).expanduser().resolve() if args.config_path else default_config_path(cwd)
    existing = load_repo_config(path=cfg_path)
    defaults = get_default_config(cwd)

    db_url = args.database_url or existing.database_url or fallback_sqlite_url(cwd)
    project = args.project or existing.project or defaults.project
    suite = args.suite or existing.suite or defaults.suite

    ensure_sqlite_parent(db_url)
    config = TrackerConfig(
        database_url=db_url,
        project=project,
        suite=suite,
        jsonl_path=existing.jsonl_path,
        config_path=cfg_path,
    )

    try:
        written = write_config(config, cfg_path, force=args.force or not cfg_path.exists())
    except FileExistsError as exc:
        print(f"{exc}; use --force to overwrite.")
        return 1

    print(f"Wrote config to {written}")

    wants_schema = not args.no_schema
    if db_url.startswith("sqlite"):
        wants_schema = not args.no_schema  # default True
    elif not args.apply_schema:
        wants_schema = False

    if wants_schema:
        try:
            asyncio.run(_create_schema(db_url))
            print("Database schema ensured.")
        except Exception as exc:  # pragma: no cover - best effort
            print(f"Failed to create schema: {exc}")
            return 2
    else:
        print("Schema creation skipped.")
    return 0
