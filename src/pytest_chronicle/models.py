from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlmodel import SQLModel, Field
from sqlalchemy import Column, String, Float, DateTime, Boolean, Text, JSON


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TestRun(SQLModel, table=True):
    __tablename__ = "test_runs"

    id: str = Field(primary_key=True)
    created_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))

    project: str = Field(sa_column=Column(String))
    suite: str = Field(sa_column=Column(String))
    status: str = Field(sa_column=Column(String))

    head_sha: str = Field(sa_column=Column(String))
    code_hash: str = Field(sa_column=Column(String))
    branch: str = Field(default="", sa_column=Column(String))
    parent_sha: str = Field(default="", sa_column=Column(String))
    origin_url: str = Field(default="", sa_column=Column(String))
    describe: str = Field(default="", sa_column=Column(String))
    commit_timestamp: str = Field(default="", sa_column=Column(String))
    is_dirty: bool = Field(default=False, sa_column=Column(Boolean))

    gpu: str = Field(default="", sa_column=Column(String))
    marks: str = Field(default="", sa_column=Column(String))
    pytest_args: str = Field(default="", sa_column=Column(String))
    platform: str = Field(default="", sa_column=Column(String))
    python_version: str = Field(default="", sa_column=Column(String))
    host: str = Field(default="", sa_column=Column(String))

    tests: int = Field(default=0)
    failures: int = Field(default=0)
    errors: int = Field(default=0)
    skipped: int = Field(default=0)
    passed: int = Field(default=0)
    time_sec: float = Field(default=0.0, sa_column=Column(Float))

    env: Any = Field(default=None, sa_column=Column(JSON))
    junit: Any = Field(default=None, sa_column=Column(JSON))
    ci: Any = Field(default=None, sa_column=Column(JSON))
    report_dir: str = Field(default="", sa_column=Column(String))

    run_key: str = Field(unique=True, index=True)


class TestCase(SQLModel, table=True):
    __tablename__ = "test_cases"

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    nodeid: str = Field(sa_column=Column(String))
    classname: str = Field(default="", sa_column=Column(String))
    name: str = Field(default="", sa_column=Column(String))
    status: str = Field(sa_column=Column(String))
    time_sec: float = Field(default=0.0, sa_column=Column(Float))
    message: str = Field(default="", sa_column=Column(String))
    detail: str = Field(default="", sa_column=Column(Text))
    stdout_text: str = Field(default="", sa_column=Column(Text))
    stderr_text: str = Field(default="", sa_column=Column(Text))
