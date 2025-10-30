"""
Configuration helpers for pytest-chronicle.

These stubs will be expanded as the Survi tooling migrates into the package.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


PRIMARY_DB_ENV = "PYTEST_RESULTS_DB_URL"
LEGACY_DB_ENVS = ("TEST_RESULTS_DATABASE_URL", "SCS_DATABASE_URL")


@dataclass(slots=True)
class TrackerConfig:
    database_url: Optional[str]
    project: Optional[str]
    suite: Optional[str]
    jsonl_path: Optional[str]


def resolve_database_url() -> Optional[str]:
    """Return the configured database URL, honoring legacy environment variables."""
    explicit = os.getenv(PRIMARY_DB_ENV)
    if explicit:
        return explicit
    for name in LEGACY_DB_ENVS:
        val = os.getenv(name)
        if val:
            return val
    return None


def get_default_config() -> TrackerConfig:
    return TrackerConfig(
        database_url=resolve_database_url(),
        project=os.getenv("PYTEST_RESULTS_PROJECT"),
        suite=os.getenv("PYTEST_RESULTS_SUITE"),
        jsonl_path=os.getenv("PYTEST_RESULTS_JSONL"),
    )
