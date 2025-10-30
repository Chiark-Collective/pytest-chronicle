from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from pytest_chronicle.cli.__main__ import main as cli_main
from pytest_chronicle.cli import run_cmd


def _write_summary(path: Path, *, status: str = "FAIL") -> Path:
    summary = {
        "status": status,
        "timestamp": "2025-01-01T00:00:00Z",
        "gpu": "cpu",
        "head_sha": "deadbeef",
        "code_hash_excluding_reports": "cafebabe",
        "report_dir": str(path.parent),
        "junit": {
            "tests": 1,
            "failures": 1 if status != "PASS" else 0,
            "errors": 0,
            "skipped": 0,
            "passed": 0 if status != "PASS" else 1,
            "time_sec": 0.01,
            "cases": [
                {
                    "classname": "pkg.mod",
                    "name": "test_failure",
                    "nodeid": "pkg/mod.py::test_failure",
                    "time_sec": 0.01,
                    "status": "failed" if status != "PASS" else "passed",
                    "message": "boom" if status != "PASS" else "",
                    "detail": "traceback" if status != "PASS" else "",
                }
            ],
        },
        "env": {"python": "3.12"},
        "marks": "",
        "pytest_args": "-q",
    }
    path.write_text(json.dumps(summary), encoding="utf-8")
    return path


@pytest.mark.parametrize("mode", ["per-test", "latest-run"])
def test_cli_ingest_and_latest_red(tmp_path: Path, mode: str, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "db.sqlite"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    summary_path = _write_summary(tmp_path / "summary.json")

    exit_ingest = cli_main(
        [
            "ingest",
            "--summary",
            str(summary_path),
            "--database-url",
            db_url,
            "--project",
            "tools/tests",
            "--suite",
            "pytest",
        ]
    )
    assert exit_ingest == 0

    exit_latest = cli_main(
        [
            "latest-red",
            "--database-url",
            db_url,
            "--mode",
            mode,
            "--project-like",
            "tools/tests%",
        ]
    )
    assert exit_latest == 0
    captured = capsys.readouterr()
    assert "pkg/mod.py::test_failure" in captured.out


def test_cli_backfill_export_import(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}"
    backfill_dir = tmp_path / "reports" / "2024-01-01"
    backfill_dir.mkdir(parents=True)
    summary_path = _write_summary(backfill_dir / "summary.json")

    exit_dry = cli_main([
        "backfill",
        "--glob",
        str(summary_path),
        "--database-url",
        db_url,
        "--dry-run",
    ])
    assert exit_dry == 0
    dry_output = capsys.readouterr().out
    assert "Found 1 file" in dry_output

    exit_backfill = cli_main([
        "backfill",
        "--glob",
        str(summary_path),
        "--database-url",
        db_url,
    ])
    assert exit_backfill == 0

    export_path = tmp_path / "exported.sqlite"
    exit_export = cli_main([
        "export-sqlite",
        "--database-url",
        db_url,
        "--out",
        str(export_path),
    ])
    assert exit_export == 0
    assert export_path.exists()

    import_db = f"sqlite+aiosqlite:///{tmp_path / 'imported.sqlite'}"
    exit_import = cli_main([
        "import-sqlite",
        "--sqlite",
        str(export_path),
        "--database-url",
        import_db,
    ])
    assert exit_import == 0

    capsys.readouterr()
    exit_latest = cli_main([
        "latest-red",
        "--database-url",
        import_db,
        "--mode",
        "per-test",
        "--project-like",
        "%",
    ])
    assert exit_latest == 0
    assert "pkg/mod.py::test_failure" in capsys.readouterr().out


def test_cli_run_invokes_pytest_and_ingests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_dir = tmp_path / "proj"
    project_dir.mkdir()

    commands: list[list[str]] = []

    def fake_run(cmd, **kwargs):  # type: ignore[override]
        if isinstance(cmd, list) and cmd[:2] == ["uv", "run"]:
            commands.append(cmd)
            return SimpleNamespace(returncode=0)
        if isinstance(cmd, list) and cmd[:2] == ["git", "-C"]:
            return SimpleNamespace(returncode=0, stdout="deadbeef\n")
        if isinstance(cmd, list) and cmd[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(returncode=0, stdout=str(tmp_path) + "\n")
        if isinstance(cmd, list) and cmd[:2] == ["git", "ls-tree"]:
            return SimpleNamespace(returncode=0, stdout="100644 blob abcdef\tproj/test_file.py\n")
        if isinstance(cmd, list) and cmd and cmd[0] in {"sha256sum", "shasum"}:
            return SimpleNamespace(returncode=0, stdout="cafebabe  -\n")
        return SimpleNamespace(returncode=0, stdout="")

    async def fake_ingest_async(**kwargs):  # type: ignore[override]
        fake_ingest_async.call_args = kwargs

    fake_ingest_async.call_args = {}  # type: ignore[attr-defined]

    monkeypatch.setattr(run_cmd, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(run_cmd, "subprocess", SimpleNamespace(run=fake_run))
    monkeypatch.setattr(run_cmd, "ingest_async", fake_ingest_async)
    monkeypatch.setattr(run_cmd, "default_database_url", lambda: "sqlite+aiosqlite:///tmp/test.db")
    monkeypatch.setattr(run_cmd, "get_default_config", lambda: SimpleNamespace(suite=None))

    jsonl_path = project_dir / ".artifacts" / "test-results" / "run.jsonl"

    exit_code = cli_main([
        "run",
        "--jsonl-path",
        str(jsonl_path),
        "proj",
        "--",
        "-k",
        "smoke",
    ])

    assert exit_code == 0
    assert commands, "uv run was not invoked"
    uv_cmd = commands[0]
    assert uv_cmd[:2] == ["uv", "run"]
    assert "pytest" in uv_cmd
    assert "--results-jsonl" in uv_cmd
    assert "tools.test_results.pytest_plugin" not in uv_cmd
    assert (project_dir / ".artifacts" / "test-results").exists()
    assert fake_ingest_async.call_args["project"] == "proj"
    assert fake_ingest_async.call_args["summary_path"] == jsonl_path


def test_cli_db_upgrade_and_revision(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}"

    exit_upgrade = cli_main([
        "db",
        "--database-url",
        db_url,
        "upgrade",
        "head",
    ])
    assert exit_upgrade == 0

    capsys.readouterr()
    exit_current = cli_main([
        "db",
        "--database-url",
        db_url,
        "current",
    ])
    assert exit_current == 0

    exit_history = cli_main([
        "db",
        "--database-url",
        db_url,
        "history",
        "--rev-range",
        "base:head",
    ])
    assert exit_history == 0

    with sqlite3.connect(tmp_path / "db.sqlite") as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_runs'").fetchone()
        assert tables is not None
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert version.endswith("_indexes_and_jsonb")

    exit_downgrade = cli_main([
        "db",
        "--database-url",
        db_url,
        "downgrade",
        "base",
    ])
    assert exit_downgrade == 0

    with sqlite3.connect(tmp_path / "db.sqlite") as conn:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_runs'").fetchone()
        assert tables is None

    exit_upgrade_again = cli_main([
        "db",
        "--database-url",
        db_url,
        "upgrade",
        "head",
    ])
    assert exit_upgrade_again == 0

    revision_dir = tmp_path / "alembic_versions"
    revision_dir.mkdir(parents=True, exist_ok=True)
    exit_revision = cli_main([
        "db",
        "--database-url",
        db_url,
        "revision",
        "--message",
        "test revision",
        "--version-path",
        str(revision_dir),
    ])
    assert exit_revision == 0
    generated = sorted(revision_dir.glob("*.py"))
    assert generated, "Expected revision script to be generated"


def test_cli_ingest_jsonl(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}"
    jsonl_path = tmp_path / "results.jsonl"
    record = {
        "nodeid": "pkg/test_sample.py::test_green",
        "duration": 0.05,
        "outcome": "failed",
        "phases": {
            "call": {
                "outcome": "failed",
                "duration": 0.05,
                "stdout": "assert False",
                "stderr": "Traceback...",
                "longrepr": "AssertionError: boom",
            }
        },
    }
    jsonl_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    exit_ingest = cli_main([
        "ingest",
        "--jsonl",
        str(jsonl_path),
        "--database-url",
        db_url,
        "--project",
        "tools/tests",
        "--suite",
        "pytest",
        "--print-id",
    ])
    assert exit_ingest == 0
    run_output = capsys.readouterr().out.strip()
    assert run_output, "Expected run_id to be printed"

    exit_latest = cli_main([
        "latest-red",
        "--database-url",
        db_url,
        "--mode",
        "per-test",
        "--project-like",
        "%",
    ])
    assert exit_latest == 0
    assert "pkg/test_sample.py::test_green" in capsys.readouterr().out
