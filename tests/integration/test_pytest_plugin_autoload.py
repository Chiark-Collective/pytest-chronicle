from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_pytest_auto_discovers_plugin(tmp_path: Path) -> None:
    """Ensure the pytest11 entry point auto-loads the plugin when installed."""

    package_root = Path(__file__).resolve().parents[2]
    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    pip_bin = venv_dir / "bin" / "pip"
    python_bin = venv_dir / "bin" / "python"
    pytest_bin = venv_dir / "bin" / "pytest"

    # Install pytest into the isolated environment (plugin discovery happens via entry points).
    subprocess.run([str(pip_bin), "install", "pytest"], check=True)

    # Install the package in editable mode (no dependencies needed for this smoke).
    subprocess.run(
        [str(pip_bin), "install", "--no-deps", "-e", str(package_root)],
        check=True,
    )

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (project_dir / "pytest.ini").write_text(
        "[pytest]\naddopts = --results-jsonl=.artifacts/results.jsonl\n", encoding="utf-8"
    )
    (project_dir / "test_example.py").write_text(
        "def test_autoload():\n    assert True\n", encoding="utf-8"
    )

    env = os.environ.copy()
    env.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)

    subprocess.run(
        [str(pytest_bin), "-q"],
        cwd=project_dir,
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    results_path = project_dir / ".artifacts" / "results.jsonl"
    assert results_path.exists(), "Plugin did not write JSONL results via auto-load"
    contents = results_path.read_text(encoding="utf-8").strip()
    assert contents, "Results JSONL was empty"
    record = json.loads(contents)
    assert record["nodeid"].endswith("test_example.py::test_autoload")
