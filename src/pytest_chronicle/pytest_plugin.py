from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from pathlib import Path

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


def pytest_configure(config) -> None:
    global _CONFIG
    _CONFIG = config
    config._results_buffer = {}
    config._results_started_at = datetime.now(timezone.utc).isoformat()
    try:
        jsonl = config.getoption("--results-jsonl")
    except Exception:
        jsonl = None
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


def pytest_runtest_logreport(report) -> None:
    config = _CONFIG
    if config is None:
        return
    rec = _ensure(config, report.nodeid)

    phase = report.when  # setup | call | teardown
    rec["phases"][phase] = {
        "outcome": report.outcome,
        "duration": getattr(report, "duration", 0.0) or 0.0,
        "stdout": _cap(_text(getattr(report, "capstdout", ""))),
        "stderr": _cap(_text(getattr(report, "capstderr", ""))),
        "longrepr": _cap(_text(getattr(report, "longreprtext", ""))),
        "sections": getattr(report, "sections", []) or [],
    }

    rec["duration"] += getattr(report, "duration", 0.0) or 0.0
    if phase == "setup":
        rec["start"] = datetime.now(timezone.utc).isoformat()
        kws = getattr(report, "keywords", {}) or {}
        rec["keywords"] = sorted(kws.keys()) if isinstance(kws, dict) else []
        rec["markers"] = [k for k in rec["keywords"] if not k.startswith("_")]
    if phase == "teardown":
        rec["end"] = datetime.now(timezone.utc).isoformat()

    if report.outcome == "failed":
        rec["outcome"] = "failed"
    elif rec["outcome"] is None or rec["outcome"] == "passed":
        rec["outcome"] = "skipped" if report.outcome == "skipped" else (rec["outcome"] or report.outcome)


def pytest_report_teststatus(report, config) -> None:
    rec = _ensure(config, report.nodeid)
    for key, value in getattr(report, "user_properties", []) or []:
        rec["user_properties"][key] = value


def pytest_terminal_summary(terminalreporter, exitstatus) -> None:
    config = terminalreporter.config
    tests = list(config._results_buffer.values())
    jsonl = config.getoption("--results-jsonl")
    endpoint = config.getoption("--results-endpoint")

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
