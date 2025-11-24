from __future__ import annotations

import os
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import SQLModel, Session, create_engine

from pytest_chronicle.cli.__main__ import main as cli_main
from pytest_chronicle.config import TrackerConfig, default_database_url, get_default_config, write_config
from pytest_chronicle.models import TestCase, TestRun


def _seed_db(db_path: Path) -> str:
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        run = TestRun(
            id="r1",
            created_at=now,
            project="proj",
            suite="suite",
            status="FAIL",
            head_sha="cafebabe",
            code_hash="hash",
            branch="main",
            parent_sha="",
            origin_url="",
            describe="",
            commit_timestamp=now.isoformat(),
            is_dirty=False,
            gpu="cpu",
            marks="smoke",
            pytest_args="-k smoke",
            platform="linux",
            python_version="3.12",
            host="localhost",
            tests=1,
            failures=1,
            errors=0,
            skipped=0,
            passed=0,
            time_sec=0.1,
            env={},
            junit={},
            ci={},
            report_dir="",
            run_key="key",
        )
        session.add(run)
        session.add(
            TestCase(
                run_id="r1",
                nodeid="pkg/test_sample.py::test_fails",
                classname="pkg.test_sample",
                name="test_fails",
                status="failed",
                time_sec=0.1,
                message="boom",
                detail="trace",
                stdout_text="out",
                stderr_text="err",
            )
        )
        session.commit()
    return f"sqlite+aiosqlite:///{db_path}"


def test_env_overrides_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg_path = tmp_path / ".pytest-chronicle.toml"
    cfg_path.write_text('[chronicle]\ndatabase_url = "sqlite+aiosqlite:///cfg.db"\nproject = "cfg"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTEST_RESULTS_DB_URL", "env-db")

    cfg = get_default_config()
    assert cfg.database_url == "env-db"
    assert cfg.config_path and cfg.config_path.name == ".pytest-chronicle.toml"


def test_default_database_url_uses_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_url = "sqlite+aiosqlite:///tmp/config.db"
    cfg_path = tmp_path / ".pytest-chronicle.toml"
    write_config(TrackerConfig(database_url=db_url, project=None, suite=None, jsonl_path=None), cfg_path, force=True)
    monkeypatch.chdir(tmp_path)
    assert default_database_url().endswith("config.db")


def test_init_creates_config_and_schema(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    exit_code = cli_main(["init", "--project", "demo", "--suite", "ci"])
    assert exit_code == 0

    cfg_path = tmp_path / ".pytest-chronicle.toml"
    assert cfg_path.exists()
    content = cfg_path.read_text()
    assert "database_url" in content
    db_line = [line for line in content.splitlines() if line.startswith("database_url")][0]
    db_url = db_line.split("=", 1)[1].strip().strip('"')
    db_path = Path(db_url.replace("sqlite+aiosqlite:///", ""))
    assert db_path.exists()

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = {row[0] for row in rows}
    assert {"test_runs", "test_cases"}.issubset(table_names)


def test_query_uses_repo_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "db.sqlite"
    db_url = _seed_db(db_path)
    cfg_path = tmp_path / ".pytest-chronicle.toml"
    write_config(TrackerConfig(database_url=db_url, project=None, suite=None, jsonl_path=None), cfg_path, force=True)
    monkeypatch.chdir(tmp_path)

    exit_code = cli_main(["query", "last-red", "--project-like", "%", "--format", "json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["items"][0]["head_sha"] == "cafebabe"


def test_config_set_creates_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "configured.db"
    exit_code = cli_main(["config", "set", "database_url", f"sqlite+aiosqlite:///{db_path}"])
    assert exit_code == 0
    cfg_path = tmp_path / ".pytest-chronicle.toml"
    assert cfg_path.exists()
    text = cfg_path.read_text()
    assert "configured.db" in text


def test_init_autodetects_project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "autodemo"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    exit_code = cli_main(["init", "--no-schema"])
    assert exit_code == 0
    cfg_path = tmp_path / ".pytest-chronicle.toml"
    assert cfg_path.exists()
    content = cfg_path.read_text()
    assert 'project = "autodemo"' in content
