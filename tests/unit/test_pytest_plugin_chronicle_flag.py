from __future__ import annotations

import sqlite3
import os
import sys
from pathlib import Path
import subprocess


def _run_pytest(tmp_path: Path, db_url: str) -> tuple[int, str, str]:
    test_file = tmp_path / "test_ok.py"
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    env = os.environ.copy()
    repo_root = Path(__file__).resolve().parents[2]
    env["PYTHONPATH"] = f"{repo_root / 'src'}" + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "pytest_chronicle.pytest_plugin",
            "--chronicle-db",
            db_url,
            "-q",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )
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
