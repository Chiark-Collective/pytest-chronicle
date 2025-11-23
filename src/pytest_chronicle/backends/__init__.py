from __future__ import annotations

from typing import Any

from pytest_chronicle.backends.base import QueryBackend, QueryParams


def resolve_backend(db_url: str) -> QueryBackend:
    from pytest_chronicle.backends.sql import SqlQueryBackend

    return SqlQueryBackend(db_url)
