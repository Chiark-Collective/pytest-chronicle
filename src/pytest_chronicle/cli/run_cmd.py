from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from pytest_chronicle.config import get_default_config
from pytest_chronicle.ingest import ingest as ingest_async, default_database_url


def configure_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "run",
        help="Run pytest for a project, capture results, and optionally ingest them.",
    )
    parser.add_argument(
        "project",
        nargs="?",
        default=".",
        help="Project path relative to the repository root (defaults to current directory).",
    )
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Arguments passed through to pytest (use -- to separate).")
    parser.add_argument("--label", "--labels", dest="labels", default=None, help="Comma-separated labels to store with the run.")
    parser.add_argument("--suite", default=None, help="(Deprecated) suite name; prefer --label/--labels.")
    parser.add_argument("--gpu", default=os.getenv("GPU", "cpu"), help="GPU label stored alongside the run (default from $GPU or cpu).")
    parser.add_argument("--skip-ingest", action="store_true", help="Only run pytest and produce artifacts; skip ingestion.")
    parser.add_argument("--database-url", help="Override database URL.")
    parser.add_argument("--uv-args", default="--extra dev", help="Arguments passed to `uv run` for executing pytest.")
    parser.add_argument("--jsonl-path", help="Optional override for JSONL output (defaults under project/.artifacts/test-results).")
    parser.add_argument("--junit-path", help="Optional override for JUnit XML output.")
    parser.add_argument("--summary-path", help="Optional override for summary JSON output.")
    return parser


def _repo_root() -> Path:
    env_override = os.getenv("PYTEST_CHRONICLE_REPO_ROOT")
    if env_override:
        return Path(env_override).expanduser().resolve()

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        git_root = proc.stdout.strip()
        if git_root:
            return Path(git_root).resolve()
    except Exception:
        pass

    return Path.cwd().resolve()


def _prepare_env(project_dir: Path, root: Path, gpu: str) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("HOME", str(root / ".home"))
    env.setdefault("UV_CACHE", str(root / ".uv_cache"))
    try:
        relative = project_dir.relative_to(root)
        identifier = relative.as_posix().replace("/", "_")
    except ValueError:
        identifier = project_dir.as_posix().replace("/", "_")
    env.setdefault("UV_PROJECT_ENVIRONMENT", str(root / ".uv_env" / identifier))
    existing_pythonpath = env.get("PYTHONPATH")
    combined_paths = [str(project_dir), str(root)]
    if existing_pythonpath:
        combined_paths.append(existing_pythonpath)
    env["PYTHONPATH"] = ":".join(combined_paths)
    env["TEST_RESULTS_GPU"] = gpu
    env.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
    return env


def _ensure_artifacts(project_dir: Path, jsonl_path: Path | None, junit_path: Path | None, summary_path: Path | None) -> tuple[Path, Path, Path]:
    artifacts = project_dir / ".artifacts" / "test-results"
    artifacts.mkdir(parents=True, exist_ok=True)
    jsonl = jsonl_path or (artifacts / "results.jsonl")
    junit = junit_path or (artifacts / "junit.xml")
    summary = summary_path or (artifacts / "summary.json")
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    junit.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    # Truncate JSONL for this run
    jsonl.write_text("", encoding="utf-8")
    return jsonl, junit, summary


def _build_uv_command(uv_args: str, pytest_args: Sequence[str], jsonl: Path, junit: Path) -> list[str]:
    base = ["uv", "run"]
    if uv_args and uv_args != "+":
        base.extend(uv_args.split())
    elif uv_args == "+":
        base.extend(["--extra", "dev"])
    base.extend(
        [
            "pytest",
            "--results-jsonl",
            str(jsonl),
            "-o",
            "junit_family=xunit2",
            "-o",
            "junit_logging=system-out",
            "-o",
            "junit_log_passing_tests=false",
            "--junitxml",
            str(junit),
        ]
    )
    base.extend(pytest_args)
    return base


def _compute_code_hash(root: Path, project_rel: str) -> str:
    git_cmd = ["git", "-C", str(root), "ls-tree", "-r", "--full-tree", "HEAD", "--", project_rel]
    proc = subprocess.run(git_cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return ""
    lines = proc.stdout.strip().splitlines()
    if not lines:
        return ""
    hash_cmd = ["sha256sum"]
    if sys.platform == "darwin":
        hash_cmd = ["shasum", "-a", "256"]
    hash_proc = subprocess.run(hash_cmd, input="\n".join(lines) + "\n", text=True, capture_output=True, check=False)
    if hash_proc.returncode != 0:
        return ""
    return hash_proc.stdout.strip().split()[0]


def _normalize_labels(labels: str | None, suite: str | None) -> str | None:
    chosen = labels or suite
    if not chosen:
        return None
    parts = [p.strip() for p in chosen.split(",") if p.strip()]
    return ",".join(parts) if parts else None


def _run_junit_to_summary(root: Path, junit: Path, summary: Path, status: str, gpu: str, code_hash: str, head_sha: str, report_dir: Path, env: dict[str, str]) -> int:
    script = root / "tools" / "junit_to_summary.py"
    if not script.exists():
        # Fallback: allow usage outside repositories that ship the helper.
        # The ingester can operate directly on JSONL when needed.
        return 0
    cmd = [
        sys.executable,
        str(script),
        "--junit",
        str(junit),
        "--out",
        str(summary),
        "--status",
        status,
        "--gpu",
        gpu,
        "--code-hash",
        code_hash,
        "--head-sha",
        head_sha,
        "--run-dir",
        str(report_dir),
    ]
    result = subprocess.run(cmd, env=env, cwd=root)
    return result.returncode


def run(args: argparse.Namespace) -> int:
    root = _repo_root()
    project_arg = Path(args.project or ".")
    if project_arg.is_absolute():
        project_dir = project_arg.resolve()
    else:
        project_dir = (root / project_arg).resolve()
    if not project_dir.exists():
        print(f"Project directory not found: {project_dir}", file=sys.stderr)
        return 2

    try:
        project_rel = project_dir.relative_to(root).as_posix()
    except ValueError:
        project_rel = project_dir.as_posix()

    jsonl_path, junit_path, summary_path = _ensure_artifacts(project_dir, args.jsonl_path and Path(args.jsonl_path), args.junit_path and Path(args.junit_path), args.summary_path and Path(args.summary_path))
    env = _prepare_env(project_dir, root, args.gpu)

    pytest_args = list(args.pytest_args or [])
    uv_cmd = _build_uv_command(args.uv_args or "+", pytest_args, jsonl_path, junit_path)
    pytest_proc = subprocess.run(uv_cmd, cwd=project_dir, env=env)
    status = "PASS" if pytest_proc.returncode == 0 else "FAIL"

    head_proc = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    head_sha = head_proc.stdout.strip() if head_proc.returncode == 0 else ""
    code_hash = _compute_code_hash(root, project_rel)
    report_dir = jsonl_path.parent
    if _run_junit_to_summary(root, junit_path, summary_path, status, args.gpu, code_hash, head_sha, report_dir, env) != 0:
        print("Failed to generate summary.json", file=sys.stderr)
        return 3

    if not args.skip_ingest:
        defaults = get_default_config()
        db_url = args.database_url or default_database_url()
        labels = _normalize_labels(args.labels, args.suite) or defaults.suite
        try:
            asyncio.run(
                ingest_async(
                    summary_path=jsonl_path,
                    database_url=db_url,
                    project=project_rel,
                    suite=labels,
                    run_id=None,
                    run_key=None,
                    print_id=False,
                    pytest_args=" ".join(pytest_args),
                )
            )
        except Exception as exc:
            print(f"Ingestion failed: {exc}", file=sys.stderr)
            return 4 if pytest_proc.returncode == 0 else pytest_proc.returncode

    return pytest_proc.returncode
