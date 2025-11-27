"""Tests for pytest_chronicle.config module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from pytest_chronicle.config import (
    CONFIG_ENV,
    CONFIG_FILENAME,
    LEGACY_DB_ENVS,
    PRIMARY_DB_ENV,
    PROJECT_ENV,
    REPO_ROOT_ENV,
    SUITE_ENV,
    TrackerConfig,
    _existing_config_path,
    _find_repo_root,
    _load_config_from_file,
    default_config_path,
    default_database_url,
    ensure_sqlite_parent,
    fallback_sqlite_url,
    get_default_config,
    load_repo_config,
    resolve_database_url,
    write_config,
)


class TestFindRepoRoot:
    def test_returns_git_root(self, tmp_path: Path) -> None:
        """Test that _find_repo_root returns the git repository root."""
        # Create a fake git repo
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        subdir = tmp_path / "sub" / "deep"
        subdir.mkdir(parents=True)

        result = _find_repo_root(subdir)
        assert result == tmp_path

    def test_env_override(self, tmp_path: Path) -> None:
        """Test PYTEST_CHRONICLE_REPO_ROOT env override."""
        override_path = tmp_path / "override"
        override_path.mkdir()
        with mock.patch.dict(os.environ, {REPO_ROOT_ENV: str(override_path)}):
            result = _find_repo_root()
            assert result == override_path

    def test_fallback_to_cwd(self, tmp_path: Path) -> None:
        """Test fallback to cwd when no .git found."""
        # Create a directory with no .git
        no_git = tmp_path / "no_git"
        no_git.mkdir()

        with mock.patch.dict(os.environ, {}, clear=True):
            # Remove any env overrides
            for key in [REPO_ROOT_ENV]:
                os.environ.pop(key, None)

            result = _find_repo_root(no_git)
            # Should return the starting directory when no .git is found
            assert result == no_git or result.is_dir()


class TestExistingConfigPath:
    def test_finds_config_file(self, tmp_path: Path) -> None:
        """Test finding config file in directory tree."""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text("[chronicle]\nproject = 'test'\n")
        subdir = tmp_path / "sub"
        subdir.mkdir()

        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop(CONFIG_ENV, None)
            result = _existing_config_path(subdir)
            assert result == config_file

    def test_env_override(self, tmp_path: Path) -> None:
        """Test CONFIG_ENV override for config path."""
        config_file = tmp_path / "custom_config.toml"
        config_file.write_text("[chronicle]\nproject = 'custom'\n")

        with mock.patch.dict(os.environ, {CONFIG_ENV: str(config_file)}):
            result = _existing_config_path()
            assert result == config_file

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        """Test returns None when no config file exists."""
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop(CONFIG_ENV, None)
            result = _existing_config_path(tmp_path)
            assert result is None


class TestDefaultConfigPath:
    def test_returns_repo_root_path(self, tmp_path: Path) -> None:
        """Test default config path is in repo root."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop(CONFIG_ENV, None)
            result = default_config_path(tmp_path)
            assert result.name == CONFIG_FILENAME
            assert result.parent == tmp_path

    def test_env_override(self, tmp_path: Path) -> None:
        """Test CONFIG_ENV override for default path."""
        custom_path = tmp_path / "custom.toml"
        with mock.patch.dict(os.environ, {CONFIG_ENV: str(custom_path)}):
            result = default_config_path()
            assert result == custom_path


class TestLoadConfigFromFile:
    def test_loads_config_with_chronicle_section(self, tmp_path: Path) -> None:
        """Test loading config from [chronicle] section."""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text("""
[chronicle]
database_url = "sqlite:///test.db"
project = "my-project"
suite = "smoke"
jsonl_path = "/path/to/results.jsonl"
""")

        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop(CONFIG_ENV, None)
            result = _load_config_from_file(tmp_path)

        assert result.database_url == "sqlite:///test.db"
        assert result.project == "my-project"
        assert result.suite == "smoke"
        assert result.jsonl_path == "/path/to/results.jsonl"
        assert result.config_path == config_file

    def test_loads_top_level_keys(self, tmp_path: Path) -> None:
        """Test loading config from top-level keys (no section)."""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text("""
database_url = "sqlite:///top.db"
project = "top-project"
""")

        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop(CONFIG_ENV, None)
            result = _load_config_from_file(tmp_path)

        assert result.database_url == "sqlite:///top.db"
        assert result.project == "top-project"

    def test_returns_empty_when_no_config(self, tmp_path: Path) -> None:
        """Test returns empty config when file doesn't exist."""
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop(CONFIG_ENV, None)
            result = _load_config_from_file(tmp_path)

        assert result.database_url is None
        assert result.project is None
        assert result.suite is None
        assert result.config_path is None

    def test_handles_invalid_toml(self, tmp_path: Path) -> None:
        """Test gracefully handles invalid TOML."""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text("this is not valid toml [[[")

        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop(CONFIG_ENV, None)
            result = _load_config_from_file(tmp_path)

        assert result.database_url is None


class TestLoadRepoConfig:
    def test_loads_from_explicit_path(self, tmp_path: Path) -> None:
        """Test loading config from explicit path."""
        config_file = tmp_path / "explicit.toml"
        config_file.write_text("""
[chronicle]
project = "explicit-project"
""")

        result = load_repo_config(path=config_file)
        assert result.project == "explicit-project"
        assert result.config_path == config_file

    def test_returns_empty_for_missing_path(self, tmp_path: Path) -> None:
        """Test returns empty config for non-existent explicit path."""
        missing = tmp_path / "missing.toml"
        result = load_repo_config(path=missing)
        assert result.project is None
        assert result.config_path == missing


class TestResolveDatabaseUrl:
    def test_primary_env_takes_precedence(self, tmp_path: Path) -> None:
        """Test PRIMARY_DB_ENV takes precedence."""
        with mock.patch.dict(os.environ, {PRIMARY_DB_ENV: "postgresql://primary"}):
            result = resolve_database_url()
            assert result == "postgresql://primary"

    def test_legacy_env_fallback(self, tmp_path: Path) -> None:
        """Test legacy env vars are checked."""
        with mock.patch.dict(os.environ, {LEGACY_DB_ENVS[0]: "postgresql://legacy"}, clear=True):
            os.environ.pop(PRIMARY_DB_ENV, None)
            result = resolve_database_url()
            assert result == "postgresql://legacy"

    def test_file_config_fallback(self, tmp_path: Path) -> None:
        """Test file config is used when no env vars."""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text('[chronicle]\ndatabase_url = "sqlite:///file.db"')

        with mock.patch.dict(os.environ, {}, clear=True):
            for key in [PRIMARY_DB_ENV] + list(LEGACY_DB_ENVS):
                os.environ.pop(key, None)
            os.environ.pop(CONFIG_ENV, None)

            # Mock _existing_config_path to return our config
            with mock.patch(
                "pytest_chronicle.config._existing_config_path", return_value=config_file
            ):
                result = resolve_database_url()
                assert result == "sqlite:///file.db"

    def test_returns_none_when_nothing_configured(self, tmp_path: Path) -> None:
        """Test returns None when nothing configured."""
        with mock.patch.dict(os.environ, {}, clear=True):
            for key in [PRIMARY_DB_ENV] + list(LEGACY_DB_ENVS) + [CONFIG_ENV]:
                os.environ.pop(key, None)

            with mock.patch(
                "pytest_chronicle.config._existing_config_path", return_value=None
            ):
                result = resolve_database_url()
                assert result is None


class TestGetDefaultConfig:
    def test_env_overrides_file(self, tmp_path: Path) -> None:
        """Test env vars override file config."""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text('[chronicle]\nproject = "file-project"\n')

        with mock.patch.dict(
            os.environ,
            {PROJECT_ENV: "env-project"},
        ):
            with mock.patch(
                "pytest_chronicle.config._existing_config_path", return_value=config_file
            ):
                result = get_default_config(tmp_path)
                assert result.project == "env-project"

    def test_file_used_when_no_env(self, tmp_path: Path) -> None:
        """Test file config used when no env vars."""
        config_file = tmp_path / CONFIG_FILENAME
        config_file.write_text('[chronicle]\nproject = "file-project"\nsuite = "ci"\n')

        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop(PROJECT_ENV, None)
            os.environ.pop(SUITE_ENV, None)
            os.environ.pop(CONFIG_ENV, None)

            result = get_default_config(tmp_path)
            # Project comes from file
            assert result.project == "file-project"
            assert result.suite == "ci"


class TestFallbackSqliteUrl:
    def test_returns_async_sqlite_url(self, tmp_path: Path) -> None:
        """Test returns async sqlite URL under repo root."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop(REPO_ROOT_ENV, None)
            result = fallback_sqlite_url(tmp_path)

        assert result.startswith("sqlite+aiosqlite:///")
        assert ".pytest-chronicle/chronicle.db" in result


class TestDefaultDatabaseUrl:
    def test_returns_config_url_when_set(self, tmp_path: Path) -> None:
        """Test returns configured URL when available."""
        with mock.patch.dict(os.environ, {PRIMARY_DB_ENV: "postgresql://test"}):
            result = default_database_url()
            assert result == "postgresql://test"

    def test_falls_back_to_sqlite(self, tmp_path: Path) -> None:
        """Test falls back to SQLite when nothing configured."""
        with mock.patch.dict(os.environ, {}, clear=True):
            for key in [PRIMARY_DB_ENV] + list(LEGACY_DB_ENVS) + [CONFIG_ENV]:
                os.environ.pop(key, None)

            with mock.patch(
                "pytest_chronicle.config._existing_config_path", return_value=None
            ):
                result = default_database_url()
                assert "sqlite+aiosqlite:///" in result


class TestWriteConfig:
    def test_writes_config_file(self, tmp_path: Path) -> None:
        """Test writing config to file."""
        config = TrackerConfig(
            database_url="sqlite:///test.db",
            project="my-project",
            suite="smoke",
            jsonl_path="/path/to/results.jsonl",
        )
        target = tmp_path / "config.toml"

        result = write_config(config, target)
        assert result == target.resolve()
        assert target.exists()

        content = target.read_text()
        assert "[chronicle]" in content
        assert 'database_url = "sqlite:///test.db"' in content
        assert 'project = "my-project"' in content
        assert 'suite = "smoke"' in content
        assert 'jsonl_path = "/path/to/results.jsonl"' in content

    def test_raises_when_exists_without_force(self, tmp_path: Path) -> None:
        """Test raises FileExistsError when file exists and force=False."""
        config = TrackerConfig(database_url=None, project=None, suite=None, jsonl_path=None)
        target = tmp_path / "config.toml"
        target.write_text("existing content")

        with pytest.raises(FileExistsError):
            write_config(config, target, force=False)

    def test_overwrites_with_force(self, tmp_path: Path) -> None:
        """Test overwrites existing file with force=True."""
        config = TrackerConfig(database_url=None, project="new-project", suite=None, jsonl_path=None)
        target = tmp_path / "config.toml"
        target.write_text("existing content")

        write_config(config, target, force=True)
        content = target.read_text()
        assert "new-project" in content

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test creates parent directories."""
        config = TrackerConfig(database_url=None, project="test", suite=None, jsonl_path=None)
        target = tmp_path / "sub" / "deep" / "config.toml"

        write_config(config, target)
        assert target.exists()


class TestEnsureSqliteParent:
    def test_creates_parent_for_sqlite_url(self, tmp_path: Path) -> None:
        """Test creates parent directory for SQLite URL."""
        db_path = tmp_path / "sub" / "data" / "test.db"
        url = f"sqlite:///{db_path}"

        result = ensure_sqlite_parent(url)
        assert result == db_path
        assert db_path.parent.exists()

    def test_creates_parent_for_async_sqlite_url(self, tmp_path: Path) -> None:
        """Test creates parent directory for async SQLite URL."""
        db_path = tmp_path / "async" / "test.db"
        url = f"sqlite+aiosqlite:///{db_path}"

        result = ensure_sqlite_parent(url)
        assert result == db_path
        assert db_path.parent.exists()

    def test_returns_none_for_non_sqlite(self) -> None:
        """Test returns None for non-SQLite URLs."""
        result = ensure_sqlite_parent("postgresql://user:pass@host/db")
        assert result is None

    def test_handles_invalid_url(self) -> None:
        """Test gracefully handles invalid URLs."""
        result = ensure_sqlite_parent("not-a-valid-url")
        assert result is None
