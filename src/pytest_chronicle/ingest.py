#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pytest_chronicle.config import (
    default_database_url as config_default_database_url,
    ensure_sqlite_parent,
    get_default_config,
)

__all__ = [
    "parse_args",
    "load_summary",
    "load_jsonl_cases",
    "_git",
    "GitInfo",
    "collect_git_info",
    "ensure_schema",
    "default_database_url",
    "detect_project",
    "detect_suite",
    "compute_run_key",
    "ci_context",
    "ingest",
    "main",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest pytest/JUnit summary into DB with git metadata")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--summary", help="Path to summary.json produced by tools/junit_to_summary.py")
    group.add_argument("--jsonl", help="Path to JSONL produced by pytest-chronicle pytest plugin")
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "SQLAlchemy URL (e.g., postgresql+asyncpg://user:pass@host:5432/db or "
            "sqlite+aiosqlite:///<repo_root>/.pytest-chronicle/chronicle.db). Defaults to PYTEST_RESULTS_DB_URL, "
            "TEST_RESULTS_DATABASE_URL, SCS_DATABASE_URL, repo config file, or sqlite+aiosqlite:///<repo_root>/.pytest-chronicle/chronicle.db"
        ),
    )
    parser.add_argument("--project", default=None, help="Logical project name (e.g., packages/survi)")
    parser.add_argument("--suite", default=None, help="Suite label (e.g., survi-gpu)")
    parser.add_argument("--run-id", default=None, help="Optional fixed run_id; otherwise a UUID4 is generated")
    parser.add_argument("--run-key", default=None, help="Idempotency key; defaults to a hash of commit/suite/project/marks/pytest_args")
    parser.add_argument("--print-id", action="store_true", help="Print the run_id on success")
    return parser.parse_args()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load_summary(path: str | os.PathLike[str]) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl_cases(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(json.loads(line))
            except Exception:
                continue
    return cases


def _git(args: list[str], cwd: str | None = None) -> str:
    try:
        out = subprocess.check_output(["git", *args], cwd=cwd or os.getcwd(), stderr=subprocess.DEVNULL)
        return out.decode().strip()
    except Exception:
        return ""


@dataclass
class GitInfo:
    head_sha: str
    branch: str
    origin_url: str
    describe: str
    commit_timestamp: str
    parent_sha: str
    is_dirty: bool


def collect_git_info(repo_root: str | None = None) -> GitInfo:
    cwd = repo_root or os.getcwd()
    head_sha = _git(["rev-parse", "HEAD"], cwd)
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    origin_url = _git(["remote", "get-url", "origin"], cwd)
    describe = _git(["describe", "--always", "--dirty", "--tags"], cwd)
    commit_timestamp = _git(["show", "-s", "--format=%cI", "HEAD"], cwd)
    parent_sha = _git(["rev-parse", "HEAD^"], cwd)
    dirty = bool(_git(["status", "--porcelain"], cwd))
    return GitInfo(
        head_sha=head_sha,
        branch=branch,
        origin_url=origin_url,
        describe=describe,
        commit_timestamp=commit_timestamp,
        parent_sha=parent_sha,
        is_dirty=dirty,
    )


async def ensure_schema(engine) -> None:
    from sqlmodel import SQLModel  # type: ignore

    from pytest_chronicle.models import TestRun, TestCase  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


def default_database_url() -> str:
    return config_default_database_url()


def detect_project(summary_path: Path) -> str:
    try:
        rel = summary_path.relative_to(Path.cwd())
        parts = rel.parts
        for i, part in enumerate(parts):
            if part in {"packages", "services", "apps", "workers", "connectors", "libs"}:
                if i + 1 < len(parts):
                    return f"{part}/{parts[i + 1]}"
        return str(summary_path.parent)
    except Exception:
        return str(summary_path.parent)


def detect_suite(summary: dict[str, Any]) -> str:
    marks = (summary.get("marks") or "").strip()
    gpu = summary.get("gpu") or ""
    if marks:
        return f"pytest{('-' + gpu) if gpu else ''}:{marks}"
    return f"pytest{('-' + gpu) if gpu else ''}"


def compute_run_key(project: str, suite: str, head_sha: str, code_hash: str, marks: str, pytest_args: str, gpu: str) -> str:
    import hashlib

    payload = f"{project}|{suite}|{head_sha}|{code_hash}|{marks}|{pytest_args}|{gpu}".encode()
    return hashlib.sha256(payload).hexdigest()


def ci_context() -> dict[str, Any]:
    env = os.environ
    keys = [
        "CI",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_NUMBER",
        "GITHUB_REF",
        "GITHUB_SHA",
        "GITHUB_REPOSITORY",
        "GITHUB_ACTOR",
        "BUILDKITE_BUILD_ID",
        "BUILDKITE_JOB_ID",
        "BUILDKITE_BRANCH",
        "BUILDKITE_COMMIT",
        "BRANCH_NAME",
    ]
    return {key: env[key] for key in keys if key in env}


async def ingest(
    summary_path: Path,
    database_url: str,
    project: str | None,
    suite: str | None,
    run_id: str | None,
    run_key: str | None,
    print_id: bool = False,
    pytest_args: str | None = None,
) -> str:
    if summary_path.suffix == ".jsonl":
        tests = load_jsonl_cases(summary_path)

        def to_case(test: dict[str, Any]) -> dict[str, Any]:
            phases = test.get("phases") or {}
            setup = phases.get("setup") or {}
            call = phases.get("call") or {}
            teardown = phases.get("teardown") or {}

            status = str(test.get("outcome") or call.get("outcome") or "passed")

            def _phase_failed(phase: dict[str, Any]) -> bool:
                outcome = (phase.get("outcome") or "").lower()
                return outcome in {"failed", "error"}

            failing_phases: list[tuple[str, dict[str, Any]]] = [
                ("setup", setup) if setup else None,
                ("call", call) if call else None,
                ("teardown", teardown) if teardown else None,
            ]
            failing_phases = [p for p in failing_phases if p and _phase_failed(p[1])]  # type: ignore[arg-type]

            def _merge(fields: list[str]) -> str:
                parts: list[str] = []
                for name, phase in (failing_phases if failing_phases else [("call", call)]):
                    if not phase:
                        continue
                    chunk_lines: list[str] = []
                    for field in fields:
                        value = phase.get(field)
                        if value:
                            chunk_lines.append(str(value))
                    if not chunk_lines:
                        continue
                    header = f"== {name} ==" if failing_phases and len(failing_phases) > 1 else ""
                    parts.append("\n".join([h for h in [header] if h] + chunk_lines))
                return "\n\n".join([part for part in parts if part])

            detail = _merge(["longrepr"]) or ""
            stdout = _merge(["stdout"]) or ""
            stderr = _merge(["stderr"]) or ""

            return {
                "classname": test.get("nodeid", "").split("::")[0],
                "name": "::".join(str(test.get("nodeid", "")).split("::")[1:]),
                "nodeid": test.get("nodeid", ""),
                "time_sec": float(test.get("duration") or call.get("duration") or 0.0),
                "status": status,
                "message": "",
                **({"detail": detail} if detail else {}),
                **({"stdout": stdout} if stdout else {}),
                **({"stderr": stderr} if stderr else {}),
            }

        cases = [to_case(t) for t in tests]
        tests_count = len(cases)
        failures = sum(1 for c in cases if c.get("status") == "failed")
        errors = sum(1 for c in cases if c.get("status") == "error")
        skipped = sum(1 for c in cases if c.get("status") == "skipped")
        passed = tests_count - failures - errors - skipped
        time_sum = sum(float(c.get("time_sec") or 0.0) for c in cases)
        git = collect_git_info()
        summary = {
            "status": "FAIL" if (failures or errors) else "PASS",
            "gpu": os.getenv("TEST_RESULTS_GPU") or os.getenv("GPU") or "cpu",
            "head_sha": git.head_sha,
            "code_hash_excluding_reports": "",
            "report_dir": str(summary_path.parent),
            "junit": {
                "tests": tests_count,
                "failures": failures,
                "errors": errors,
                "skipped": skipped,
                "passed": passed,
                "time_sec": time_sum,
                "cases": cases,
            },
            "env": {},
            "marks": "",
            "pytest_args": pytest_args or "",
        }
    else:
        summary = load_summary(summary_path)
        git = collect_git_info()

    project = project or detect_project(summary_path)
    suite = suite or detect_suite(summary)

    rid = run_id or str(uuid.uuid4())
    run_key = run_key or compute_run_key(
        project=project,
        suite=suite,
        head_sha=summary.get("head_sha", git.head_sha),
        code_hash=summary.get("code_hash_excluding_reports", ""),
        marks=str(summary.get("marks", "")),
        pytest_args=str(summary.get("pytest_args", "")),
        gpu=str(summary.get("gpu", "")),
    )

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession  # type: ignore
    from sqlalchemy.orm import sessionmaker  # type: ignore
    from sqlalchemy import select  # type: ignore
    from pytest_chronicle.models import TestRun, TestCase  # type: ignore

    ensure_sqlite_parent(database_url)
    engine = create_async_engine(database_url, pool_pre_ping=True)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await ensure_schema(engine)

    async with Session() as session:
        existing = (await session.execute(select(TestRun).where(TestRun.run_key == run_key))).scalars().first()
        if existing:
            rid = existing.id
        else:
            junit = summary.get("junit", {})
            env = summary.get("env", {})
            test_run = TestRun(
                id=rid,
                project=project,
                suite=suite,
                status=str(summary.get("status", "")).upper() or "UNKNOWN",
                head_sha=str(summary.get("head_sha", git.head_sha)),
                code_hash=str(summary.get("code_hash_excluding_reports", "")),
                branch=git.branch,
                parent_sha=git.parent_sha,
                origin_url=git.origin_url,
                describe=git.describe,
                commit_timestamp=git.commit_timestamp,
                is_dirty=git.is_dirty,
                gpu=str(summary.get("gpu", "")),
                marks=str(summary.get("marks", "")),
                pytest_args=str(summary.get("pytest_args", pytest_args or "")),
                platform=platform.platform(),
                python_version=platform.python_version(),
                host=platform.node(),
                tests=int(junit.get("tests", 0) or 0),
                failures=int(junit.get("failures", 0) or 0),
                errors=int(junit.get("errors", 0) or 0),
                skipped=int(junit.get("skipped", 0) or 0),
                passed=int(junit.get("passed", 0) or 0),
                time_sec=float(junit.get("time_sec", 0.0) or 0.0),
                env=env,
                junit=junit,
                ci=ci_context(),
                report_dir=str(summary.get("report_dir", "")),
                run_key=run_key,
            )
            session.add(test_run)
            for case in junit.get("cases", []) or []:
                session.add(
                    TestCase(
                        run_id=rid,
                        nodeid=str(case.get("nodeid", "")),
                        classname=str(case.get("classname", "")),
                        name=str(case.get("name", "")),
                        status=str(case.get("status", "")),
                        time_sec=float(case.get("time_sec", 0.0) or 0.0),
                        message=str(case.get("message", "")),
                        detail=str(case.get("detail", "")),
                        stdout_text=str(case.get("stdout", "")),
                        stderr_text=str(case.get("stderr", "")),
                    )
                )
            await session.commit()

    await engine.dispose()
    if print_id:
        print(rid)
    return rid


def main() -> int:
    args = parse_args()
    db_url = (args.database_url or default_database_url()).strip()
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if db_url.startswith("sqlite:///") and "+aiosqlite" not in db_url:
        db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    defaults = get_default_config()
    try:
        path_str = args.summary or args.jsonl
        assert path_str, "Either --summary or --jsonl must be provided"
        asyncio.run(
            ingest(
                summary_path=Path(path_str),
                database_url=db_url,
                project=args.project or defaults.project,
                suite=args.suite or defaults.suite,
                run_id=args.run_id,
                run_key=args.run_key,
                print_id=args.print_id,
            )
        )
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Error ingesting test results: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
