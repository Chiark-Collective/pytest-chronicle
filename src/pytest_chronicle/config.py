"""
Configuration helpers for pytest-chronicle.

The CLI and pytest plugin honour a layered configuration model:

1. CLI flags (highest precedence)
2. Environment variables (``PYTEST_RESULTS_DB_URL``, ``PYTEST_RESULTS_PROJECT``, etc.)
3. Repository config file (``.pytest-chronicle.toml``)
4. Built-in fallback to an async SQLite database under the repo root.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:  # Python 3.11+ ships tomllib; keep a fallback for older runtimes.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib  # type: ignore


PRIMARY_DB_ENV = "PYTEST_RESULTS_DB_URL"
LEGACY_DB_ENVS = ("TEST_RESULTS_DATABASE_URL", "SCS_DATABASE_URL")
PROJECT_ENV = "PYTEST_RESULTS_PROJECT"
SUITE_ENV = "PYTEST_RESULTS_SUITE"
JSONL_ENV = "PYTEST_RESULTS_JSONL"

CONFIG_ENV = "PYTEST_CHRONICLE_CONFIG"
CONFIG_FILENAME = ".pytest-chronicle.toml"
REPO_ROOT_ENV = "PYTEST_CHRONICLE_REPO_ROOT"


@dataclass(slots=True)
class TrackerConfig:
    database_url: Optional[str]
    project: Optional[str]
    suite: Optional[str]
    jsonl_path: Optional[str]
    config_path: Optional[Path] = None


def _find_repo_root(cwd: Path | None = None) -> Path:
    env_override = os.getenv(REPO_ROOT_ENV)
    if env_override:
        return Path(env_override).expanduser().resolve()

    start = Path(cwd or Path.cwd()).resolve()
    # Prefer git metadata when available.
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            stderr=subprocess.DEVNULL,
        )
        path = Path(out.decode().strip())
        if path.exists():
            return path.resolve()
    except Exception:
        pass

    # Fall back to the first ancestor that contains a .git directory.
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate

    return start


def _existing_config_path(cwd: Path | None = None) -> Path | None:
    env_path = os.getenv(CONFIG_ENV)
    if env_path:
        candidate = Path(env_path).expanduser().resolve()
        return candidate if candidate.exists() else None

    start = Path(cwd or Path.cwd()).resolve()
    for candidate in (start, *start.parents):
        path = candidate / CONFIG_FILENAME
        if path.exists():
            return path
    return None


def default_config_path(cwd: Path | None = None) -> Path:
    """Return the preferred path to write a repo-local config file."""
    env_path = os.getenv(CONFIG_ENV)
    if env_path:
        return Path(env_path).expanduser().resolve()
    root = _find_repo_root(cwd)
    return (root / CONFIG_FILENAME).resolve()


def _load_config_from_file(cwd: Path | None = None) -> TrackerConfig:
    path = _existing_config_path(cwd)
    if not path:
        return TrackerConfig(database_url=None, project=None, suite=None, jsonl_path=None, config_path=None)

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except Exception:
        data = {}
    # allow either top-level keys or a [chronicle] table
    if isinstance(data, dict):
        section = data.get("chronicle", data)
    else:
        section = {}

    def _get(key: str) -> Optional[str]:
        val = section.get(key) if isinstance(section, dict) else None
        return str(val) if val is not None else None

    return TrackerConfig(
        database_url=_get("database_url"),
        project=_get("project"),
        suite=_get("suite"),
        jsonl_path=_get("jsonl_path"),
        config_path=path,
    )


def load_repo_config(cwd: Path | None = None, path: Path | None = None) -> TrackerConfig:
    """Load config strictly from file (no env overrides)."""
    if path:
        target = Path(path).expanduser().resolve()
        if not target.exists():
            return TrackerConfig(database_url=None, project=None, suite=None, jsonl_path=None, config_path=target)
        try:
            with target.open("rb") as handle:
                data = tomllib.load(handle)
        except Exception:
            data = {}
        section = data.get("chronicle", data) if isinstance(data, dict) else {}

        def _get(key: str) -> Optional[str]:
            val = section.get(key) if isinstance(section, dict) else None
            return str(val) if val is not None else None

        return TrackerConfig(
            database_url=_get("database_url"),
            project=_get("project"),
            suite=_get("suite"),
            jsonl_path=_get("jsonl_path"),
            config_path=target,
        )
    return _load_config_from_file(cwd)


def resolve_database_url() -> Optional[str]:
    """Return a database URL from environment variables or the repo config file."""
    explicit = os.getenv(PRIMARY_DB_ENV)
    if explicit:
        return explicit
    for name in LEGACY_DB_ENVS:
        val = os.getenv(name)
        if val:
            return val
    file_cfg = _load_config_from_file()
    if file_cfg.database_url:
        return file_cfg.database_url
    return None


def get_default_config(cwd: Path | None = None) -> TrackerConfig:
    """Resolve configuration from env > repo config > empty defaults."""
    file_cfg = _load_config_from_file(cwd)
    env_cfg = TrackerConfig(
        database_url=None,
        project=os.getenv(PROJECT_ENV),
        suite=os.getenv(SUITE_ENV),
        jsonl_path=os.getenv(JSONL_ENV),
        config_path=file_cfg.config_path,
    )
    # Database URL is special: env + legacy envs first, then file.
    env_db = os.getenv(PRIMARY_DB_ENV) or next((os.getenv(v) for v in LEGACY_DB_ENVS if os.getenv(v)), None)

    return TrackerConfig(
        database_url=env_db or file_cfg.database_url,
        project=env_cfg.project or file_cfg.project,
        suite=env_cfg.suite or file_cfg.suite,
        jsonl_path=env_cfg.jsonl_path or file_cfg.jsonl_path,
        config_path=file_cfg.config_path,
    )


def fallback_sqlite_url(cwd: Path | None = None) -> str:
    """
    Provide a deterministic default SQLite URL under the repository root.

    We prefer an async driver (`sqlite+aiosqlite`) so ingestion can reuse it directly.
    """
    root = _find_repo_root(cwd)
    db_path = (root / ".pytest-chronicle" / "chronicle.db").resolve()
    return f"sqlite+aiosqlite:///{db_path.as_posix()}"


def default_database_url(cwd: Path | None = None) -> str:
    """Return the effective database URL using env/config overrides and a SQLite fallback."""
    cfg = get_default_config(cwd)
    if cfg.database_url:
        return cfg.database_url
    return fallback_sqlite_url(cwd)


def write_config(config: TrackerConfig, path: Path | None = None, *, force: bool = False) -> Path:
    """
    Write a repo-local config file.

    The file is small; we avoid adding a new dependency for writing TOML.
    """
    target = Path(path) if path else default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        raise FileExistsError(f"{target} already exists (use --force to overwrite)")

    lines = ["[chronicle]"]
    if config.database_url:
        lines.append(f'database_url = "{config.database_url}"')
    if config.project:
        lines.append(f'project = "{config.project}"')
    if config.suite:
        lines.append(f'suite = "{config.suite}"')
    if config.jsonl_path:
        lines.append(f'jsonl_path = "{config.jsonl_path}"')

    content = "\n".join(lines) + ("\n" if lines else "")
    target.write_text(content, encoding="utf-8")
    return target.resolve()


def ensure_sqlite_parent(db_url: str) -> Path | None:
    """Create parent directories for SQLite URLs to avoid connect failures."""
    try:
        from sqlalchemy.engine.url import make_url  # type: ignore
    except Exception:
        return None
    try:
        url = make_url(db_url)
    except Exception:
        return None
    if not url.drivername.startswith("sqlite"):
        return None
    db_path = Path(url.database or "")
    if not db_path.is_absolute():
        db_path = (Path.cwd() / db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path
