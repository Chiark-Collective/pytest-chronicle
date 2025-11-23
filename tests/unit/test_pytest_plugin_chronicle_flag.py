from __future__ import annotations

import os
import sys
from pathlib import Path
import subprocess
import sqlite3


def _run_pytest(tmp_path: Path, db_url: str | None) -> tuple[int, str, str]:
    test_file = tmp_path / "test_ok.py"
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    env = os.environ.copy()
    repo_root = Path(__file__).resolve().parents[2]
    env["PYTHONPATH"] = f"{repo_root / 'src'}" + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "pytest_chronicle.pytest_plugin",
        "-q",
    ]
    if db_url:
        cmd.extend(["--chronicle-db", db_url])
    proc = subprocess.run(cmd, cwd=tmp_path, env=env, text=True, capture_output=True)
    return proc.returncode, proc.stdout, proc.stderr


def test_chronicle_flag_ingests(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    code, out, err = _run_pytest(tmp_path, f"sqlite+aiosqlite:///{db_path}")
    assert code == 0, f"pytest failed: {out}\n{err}"
    assert db_path.exists(), "database was not created"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM test_runs").fetchone()[0]
    assert rows == 1


def test_chronicle_flag_accepts_sync_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "db2.sqlite"
    code, out, err = _run_pytest(tmp_path, f"sqlite:///{db_path}")
    assert code == 0, f"pytest failed: {out}\n{err}"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM test_runs").fetchone()[0]
    assert rows == 1


def test_plugin_uses_repo_config_when_flag_absent(tmp_path: Path) -> None:
    db_path = tmp_path / "auto.sqlite"
    (tmp_path / ".pytest-chronicle.toml").write_text(
        f'[chronicle]\ndatabase_url = "sqlite+aiosqlite:///{db_path}"\n',
        encoding="utf-8",
    )
    code, out, err = _run_pytest(tmp_path, None)
    assert code == 0, f"pytest failed: {out}\n{err}"
    assert db_path.exists(), "database was not created via repo config"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM test_runs").fetchone()[0]
    assert rows == 1


def test_plugin_falls_back_to_default_sqlite(tmp_path: Path) -> None:
    code, out, err = _run_pytest(tmp_path, None)
    assert code == 0, f"pytest failed: {out}\n{err}"
    db_path = tmp_path / ".pytest-chronicle" / "chronicle.db"
    assert db_path.exists(), "default sqlite database was not created"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM test_runs").fetchone()[0]
    assert rows == 1
