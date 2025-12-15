from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pytest_chronicle.config import get_default_config, default_database_url

try:
    import requests  # optional dependency
except Exception:  # pragma: no cover - optional dependency
    requests = None  # type: ignore[assignment]

__all__ = [
    "pytest_addoption",
    "pytest_configure",
    "pytest_runtest_logreport",
    "pytest_report_teststatus",
    "pytest_terminal_summary",
]

_CONFIG: Any | None = None


def _to_async_url(db_url: str) -> str:
    if db_url.startswith("postgresql://"):
        return db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if db_url.startswith("sqlite:///") and "+aiosqlite" not in db_url:
        return db_url.replace("sqlite:///", "sqlite+aiosqlite:///")
    return db_url


def _ingest_from_jsonl(
    terminalreporter,
    *,
    jsonl_path: Path,
    database_url: str,
    project: str | None,
    suite: str | None,
    pytest_args: str | None,
) -> None:
    try:
        from pytest_chronicle.ingest import ingest as ingest_async
    except Exception as exc:  # pragma: no cover - import guard
        terminalreporter.write_line(f"[chronicle] ingest import failed: {exc}", red=True)
        return

    db_url = _to_async_url(database_url)
    try:
        asyncio.run(
            ingest_async(
                summary_path=jsonl_path,
                database_url=db_url,
                project=project,
                suite=suite,
                run_id=None,
                run_key=None,
                print_id=False,
                pytest_args=pytest_args,
            )
        )
        terminalreporter.write_line(f"[chronicle] ingested run into {database_url}")
    except Exception as exc:  # pragma: no cover - best effort
        terminalreporter.write_line(f"[chronicle] ingest failed: {exc}", red=True)


def pytest_addoption(parser) -> None:
    group = parser.getgroup("results-export")
    group.addoption(
        "--results-endpoint",
        action="store",
        default=None,
        help="HTTP endpoint to POST results as JSON (batch at end).",
    )
    group.addoption(
        "--results-jsonl",
        action="store",
        default=None,
        help="Write per-test JSON lines to this file (appended).",
    )

    chronicle = parser.getgroup("chronicle")
    chronicle.addoption("--chronicle-db", action="store", default=None, help="Database URL to auto-ingest results at session end.")
    chronicle.addoption("--chronicle-project", action="store", default=None, help="Override project name for ingestion.")
    chronicle.addoption("--chronicle-suite", action="store", default=None, help="Override suite name for ingestion.")
    chronicle.addoption("--chronicle-no-ingest", action="store_true", help="Disable auto-ingestion even if --chronicle-db is set.")


def pytest_configure(config) -> None:
    global _CONFIG
    _CONFIG = config
    defaults = get_default_config()
    config._results_buffer = {}
    config._results_started_at = datetime.now(timezone.utc).isoformat()
    try:
        jsonl = config.getoption("--results-jsonl")
    except Exception:
        jsonl = None

    chronicle_db = getattr(config.option, "chronicle_db", None) or defaults.database_url or default_database_url()
    if chronicle_db and not jsonl:
        default_jsonl = Path.cwd() / ".artifacts" / "test-results" / "chronicle-results.jsonl"
        default_jsonl.parent.mkdir(parents=True, exist_ok=True)
        setattr(config.option, "results_jsonl", str(default_jsonl))
        jsonl = str(default_jsonl)

    if jsonl:
        try:
            with open(jsonl, "w", encoding="utf-8"):
                pass
        except Exception:
            pass  # best effort


def _ensure(config, nodeid: str) -> dict[str, Any]:
    return config._results_buffer.setdefault(
        nodeid,
        {
            "nodeid": nodeid,
            "start": None,
            "end": None,
            "outcome": None,
            "duration": 0.0,
            "phases": {},
            "keywords": [],
            "markers": [],
            "user_properties": {},
        },
    )


def _text(val: Any) -> str:
    try:
        if val is None:
            return ""
        return str(val)
    except Exception:
        return ""


def _cap(value: str, n: int = 20000) -> str:
    if not value:
        return ""
    return value if len(value) <= n else (value[:n] + "\n... [truncated]")


def _resolve_outcome(report) -> str:
    """Resolve the test outcome, detecting xfail/xpass cases.

    Pytest marks xfail tests with a 'wasxfail' attribute on the report:
    - xfail (expected failure that failed): outcome='skipped', wasxfail=reason
    - xpass (expected failure that passed): outcome='passed', wasxfail=reason
    - strict xpass becomes outcome='failed' (no special handling needed)
    """
    outcome = report.outcome
    if hasattr(report, "wasxfail"):
        if outcome == "skipped":
            return "xfailed"
        elif outcome == "passed":
            return "xpassed"
    return outcome


def pytest_runtest_logreport(report) -> None:
    config = _CONFIG
    if config is None:
        return
    rec = _ensure(config, report.nodeid)

    phase = report.when  # setup | call | teardown
    phase_outcome = _resolve_outcome(report)
    rec["phases"][phase] = {
        "outcome": phase_outcome,
        "duration": getattr(report, "duration", 0.0) or 0.0,
        "stdout": _cap(_text(getattr(report, "capstdout", ""))),
        "stderr": _cap(_text(getattr(report, "capstderr", ""))),
        "longrepr": _cap(_text(getattr(report, "longreprtext", ""))),
        "sections": getattr(report, "sections", []) or [],
        "wasxfail": getattr(report, "wasxfail", None),
    }

    rec["duration"] += getattr(report, "duration", 0.0) or 0.0
    if phase == "setup":
        rec["start"] = datetime.now(timezone.utc).isoformat()
        kws = getattr(report, "keywords", {}) or {}
        rec["keywords"] = sorted(kws.keys()) if isinstance(kws, dict) else []
        rec["markers"] = [k for k in rec["keywords"] if not k.startswith("_")]
    if phase == "teardown":
        rec["end"] = datetime.now(timezone.utc).isoformat()

    # Determine overall test outcome with xfail/xpass awareness
    if phase_outcome == "failed":
        rec["outcome"] = "failed"
    elif phase_outcome == "xfailed":
        # xfailed takes precedence over passed but not over failed
        if rec["outcome"] not in ("failed",):
            rec["outcome"] = "xfailed"
    elif phase_outcome == "xpassed":
        # xpassed takes precedence over passed but not over failed/xfailed
        if rec["outcome"] not in ("failed", "xfailed"):
            rec["outcome"] = "xpassed"
    elif rec["outcome"] is None or rec["outcome"] == "passed":
        rec["outcome"] = "skipped" if phase_outcome == "skipped" else (rec["outcome"] or phase_outcome)


def pytest_report_teststatus(report, config) -> None:
    rec = _ensure(config, report.nodeid)
    for key, value in getattr(report, "user_properties", []) or []:
        rec["user_properties"][key] = value


def pytest_terminal_summary(terminalreporter, exitstatus) -> None:
    config = terminalreporter.config
    tests = list(config._results_buffer.values())
    jsonl = config.getoption("--results-jsonl")
    endpoint = config.getoption("--results-endpoint")
    defaults = get_default_config()
    chronicle_db = getattr(config.option, "chronicle_db", None) or defaults.database_url or default_database_url()
    chronicle_project = getattr(config.option, "chronicle_project", None) or defaults.project
    chronicle_suite = getattr(config.option, "chronicle_suite", None) or defaults.suite
    chronicle_no = getattr(config.option, "chronicle_no_ingest", False)
    try:
        invocation = getattr(config, "invocation_params", None)
        pytest_args = " ".join(invocation.args) if invocation and invocation.args else ""
    except Exception:
        pytest_args = ""

    if jsonl:
        jsonl_path = Path(jsonl)
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with jsonl_path.open("a", encoding="utf-8") as handle:
            for test in tests:
                handle.write(json.dumps(test, ensure_ascii=False) + "\n")
        terminalreporter.write_line(f"[results-export] wrote {len(tests)} tests to {jsonl_path}")

    if endpoint:
        if requests is None:
            terminalreporter.write_line("[results-export] requests not available; cannot POST", yellow=True)
            return
        try:
            response = requests.post(endpoint, json={"tests": tests, "exitstatus": exitstatus}, timeout=20)
            response.raise_for_status()
            terminalreporter.write_line(f"[results-export] POSTed {len(tests)} tests to {endpoint}")
        except Exception as exc:  # pragma: no cover - best effort
            terminalreporter.write_line(f"[results-export] POST failed: {exc}", red=True)

    if chronicle_db and not chronicle_no and jsonl:
        _ingest_from_jsonl(
            terminalreporter,
            jsonl_path=Path(jsonl),
            database_url=chronicle_db,
            project=chronicle_project,
            suite=chronicle_suite,
            pytest_args=pytest_args,
        )
