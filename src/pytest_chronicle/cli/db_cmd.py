from __future__ import annotations

import argparse
from importlib import resources
from typing import Optional

from alembic import command  # type: ignore
from alembic.config import Config  # type: ignore

from pytest_chronicle.config import ensure_sqlite_parent, resolve_database_url
from pytest_chronicle.ingest import default_database_url


def _script_location() -> str:
    return str(resources.files("pytest_chronicle") / "alembic")


def _default_versions_path() -> str:
    return str(resources.files("pytest_chronicle") / "alembic" / "versions")


def _to_sync_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("sqlite+aiosqlite://"):
        return url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    return url


def _resolve_database_url(explicit: Optional[str]) -> str:
    candidate = explicit or resolve_database_url() or default_database_url()
    ensure_sqlite_parent(candidate)
    return _to_sync_url(candidate)


def _build_config(database_url: Optional[str]) -> Config:
    config = Config()
    config.set_main_option("script_location", _script_location())
    config.set_main_option("version_locations", _default_versions_path())

    url = _resolve_database_url(database_url)
    config.set_main_option("sqlalchemy.url", url)
    config.set_section_option(config.config_ini_section, "sqlalchemy.url", url)
    return config


def configure_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "db",
        help="Manage pytest-chronicle database migrations via Alembic.",
    )
    parser.add_argument("--database-url", help="Override database URL (defaults to env or sqlite fallback).")
    db_sub = parser.add_subparsers(dest="db_command", required=True)

    upgrade = db_sub.add_parser("upgrade", help="Upgrade the database to the target revision (default: head).")
    upgrade.add_argument("revision", nargs="?", default="head")
    upgrade.add_argument("--sql", action="store_true", help="Emit SQL instead of applying migrations.")
    upgrade.add_argument("--tag", help="Tag the revision during offline generation.")

    downgrade = db_sub.add_parser("downgrade", help="Downgrade the database to a prior revision.")
    downgrade.add_argument("revision")
    downgrade.add_argument("--sql", action="store_true", help="Emit SQL instead of applying migrations.")
    downgrade.add_argument("--tag", help="Tag the revision during offline generation.")

    current = db_sub.add_parser("current", help="Display the current revision.")
    current.add_argument("--verbose", action="store_true", help="Show additional revision detail.")

    history = db_sub.add_parser("history", help="Show revision history.")
    history.add_argument("--rev-range", help="Revision range, e.g. base:head.")

    stamp = db_sub.add_parser("stamp", help="Stamp the database with a specific revision without running migrations.")
    stamp.add_argument("revision")

    revision = db_sub.add_parser("revision", help="Create a new revision script (development use).")
    revision.add_argument("-m", "--message", required=True, help="Commit message for the revision.")
    revision.add_argument("--autogenerate", action="store_true", help="Populate script using autogeneration.")
    revision.add_argument("--sql", action="store_true", help="Emit SQL instead of writing a script.")
    revision.add_argument("--head", help="Specify head revision to use as the parent.")
    revision.add_argument("--splice", action="store_true", help="Create a branch from the head.")
    revision.add_argument("--branch-label", help="Assign a branch label to the new revision.")
    revision.add_argument("--version-path", help="Alternate versions directory inside script location.")
    revision.add_argument("--rev-id", help="Hardcode revision identifier.")
    revision.add_argument("--depends-on", action="append", help="Revision dependencies.")

    return parser


def run(args: argparse.Namespace) -> int:
    config = _build_config(args.database_url)
    command_name = args.db_command

    if command_name == "upgrade":
        command.upgrade(config, args.revision, sql=args.sql, tag=args.tag)
        return 0

    if command_name == "downgrade":
        command.downgrade(config, args.revision, sql=args.sql, tag=args.tag)
        return 0

    if command_name == "current":
        command.current(config, verbose=args.verbose)
        return 0

    if command_name == "history":
        command.history(config, rev_range=args.rev_range)
        return 0

    if command_name == "stamp":
        command.stamp(config, args.revision)
        return 0

    if command_name == "revision":
        if args.version_path:
            combined_locations = " ".join([_default_versions_path(), args.version_path])
            config.set_main_option("version_locations", combined_locations)
        command.revision(
            config,
            message=args.message,
            autogenerate=args.autogenerate,
            sql=args.sql,
            head=args.head,
            splice=args.splice,
            branch_label=args.branch_label,
            version_path=args.version_path,
            rev_id=args.rev_id,
            depends_on=args.depends_on,
        )
        return 0

    raise ValueError(f"Unsupported db command: {command_name}")
