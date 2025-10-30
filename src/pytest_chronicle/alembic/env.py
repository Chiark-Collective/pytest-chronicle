"""Alembic environment for pytest-chronicle."""

from __future__ import annotations

import logging
from typing import Any, Dict

from alembic import context  # type: ignore
from sqlalchemy import engine_from_config, pool  # type: ignore
from sqlmodel import SQLModel  # type: ignore

from pytest_chronicle.models import TestRun, TestCase  # noqa: F401


logger = logging.getLogger("alembic.env")
config = context.config

# Ensure metadata includes imported models
target_metadata = SQLModel.metadata


def _get_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        raise RuntimeError("sqlalchemy.url is not configured for Alembic")
    return url


def _connection_options() -> Dict[str, Any]:
    section = config.get_section(config.config_ini_section)
    if not section:
        return {"sqlalchemy.url": _get_url()}
    return section


def run_migrations_offline() -> None:
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        _connection_options(),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:  # type: ignore[attr-defined]
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
