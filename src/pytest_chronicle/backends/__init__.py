from __future__ import annotations

from pytest_chronicle.backends.base import QueryBackend, QueryParams as QueryParams
from pytest_chronicle.config import ensure_sqlite_parent


def resolve_backend(db_url: str) -> QueryBackend:
    from pytest_chronicle.backends.sql import SqlQueryBackend

    ensure_sqlite_parent(db_url)
    return SqlQueryBackend(db_url)
