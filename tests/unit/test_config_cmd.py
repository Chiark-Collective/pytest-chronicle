"""Tests for pytest_chronicle.cli.config_cmd module."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest import mock

import pytest

from pytest_chronicle.cli.config_cmd import (
    _emit_set,
    _emit_show,
    _mask,
    configure_parser,
    run,
)
from pytest_chronicle.config import TrackerConfig


class TestMask:
    def test_masks_url_with_credentials(self) -> None:
        """Test masking credentials in URLs."""
        url = "postgresql://user:secret@host:5432/db"
        result = _mask(url)
        assert "***" in result
        assert "secret" not in result
        assert "user" not in result
        assert "@host:5432/db" in result

    def test_preserves_url_without_credentials(self) -> None:
        """Test URLs without credentials are preserved."""
        url = "sqlite:///path/to/db.sqlite"
        result = _mask(url)
        assert result == url

    def test_handles_none(self) -> None:
        """Test None returns empty string."""
        assert _mask(None) == ""

    def test_handles_plain_string(self) -> None:
        """Test plain strings are returned unchanged."""
        assert _mask("plain-value") == "plain-value"

    def test_handles_malformed_url(self) -> None:
        """Test malformed URLs with @ are handled."""
        # Has @ and :// but not in standard format
        url = "weird://value@"
        result = _mask(url)
        # Should still work or return original
        assert result is not None


class TestConfigureParser:
    def test_creates_subcommands(self) -> None:
        """Test configure_parser creates expected subcommands."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        configure_parser(subparsers)

        # Should be able to parse config show
        args = parser.parse_args(["config", "show"])
        assert args.config_command == "show"

        # Should be able to parse config set
        args = parser.parse_args(["config", "set", "project", "my-project"])
        assert args.config_command == "set"
        assert args.key == "project"
        assert args.value == "my-project"

    def test_show_format_option(self) -> None:
        """Test show subcommand has format option."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        configure_parser(subparsers)

        args = parser.parse_args(["config", "show", "--format", "json"])
        assert args.format == "json"

    def test_set_accepts_valid_keys(self) -> None:
        """Test set accepts valid configuration keys."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        configure_parser(subparsers)

        for key in ["database_url", "project", "suite", "jsonl_path"]:
            args = parser.parse_args(["config", "set", key, "value"])
            assert args.key == key


class TestEmitShow:
    def test_text_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test show in text format."""
        args = argparse.Namespace(format="text")

        config = TrackerConfig(
            database_url="sqlite:///test.db",
            project="my-project",
            suite="ci",
            jsonl_path=None,
            config_path=Path("/repo/.pytest-chronicle.toml"),
        )

        with mock.patch("pytest_chronicle.cli.config_cmd.get_default_config", return_value=config):
            result = _emit_show(args)

        assert result == 0
        captured = capsys.readouterr()
        assert "my-project" in captured.out
        assert "ci" in captured.out
        assert "test.db" in captured.out

    def test_json_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test show in JSON format."""
        args = argparse.Namespace(format="json")

        config = TrackerConfig(
            database_url="sqlite:///test.db",
            project="my-project",
            suite="ci",
            jsonl_path="/path/to/jsonl",
            config_path=Path("/repo/.pytest-chronicle.toml"),
        )

        with mock.patch("pytest_chronicle.cli.config_cmd.get_default_config", return_value=config):
            result = _emit_show(args)

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["project"] == "my-project"
        assert data["suite"] == "ci"
        assert data["database_url"] == "sqlite:///test.db"
        assert data["jsonl_path"] == "/path/to/jsonl"

    def test_shows_not_set_for_none_values(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test shows (not set) for None values in text format."""
        args = argparse.Namespace(format="text")

        config = TrackerConfig(
            database_url=None,
            project=None,
            suite=None,
            jsonl_path=None,
            config_path=None,
        )

        with mock.patch("pytest_chronicle.cli.config_cmd.get_default_config", return_value=config):
            _emit_show(args)

        captured = capsys.readouterr()
        assert "(not set)" in captured.out


class TestEmitSet:
    def test_sets_project(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Test setting project value."""
        config_file = tmp_path / ".pytest-chronicle.toml"

        args = argparse.Namespace(
            key="project",
            value="new-project",
            config_path=str(config_file),
        )

        result = _emit_set(args)
        assert result == 0
        assert config_file.exists()

        content = config_file.read_text()
        assert "new-project" in content

        captured = capsys.readouterr()
        assert "Wrote project" in captured.out

    def test_sets_database_url(self, tmp_path: Path) -> None:
        """Test setting database_url value."""
        config_file = tmp_path / ".pytest-chronicle.toml"

        args = argparse.Namespace(
            key="database_url",
            value="postgresql://host/db",
            config_path=str(config_file),
        )

        _emit_set(args)
        content = config_file.read_text()
        assert "postgresql://host/db" in content

    def test_clears_value_with_empty_string(self, tmp_path: Path) -> None:
        """Test clearing a value with empty string."""
        config_file = tmp_path / ".pytest-chronicle.toml"
        config_file.write_text('[chronicle]\nproject = "old-project"\n')

        args = argparse.Namespace(
            key="project",
            value="",  # Empty string clears the value
            config_path=str(config_file),
        )

        _emit_set(args)
        content = config_file.read_text()
        # Empty value means project line should not be present
        assert 'project = ""' not in content

    def test_preserves_existing_values(self, tmp_path: Path) -> None:
        """Test setting one value preserves others."""
        config_file = tmp_path / ".pytest-chronicle.toml"
        config_file.write_text('[chronicle]\ndatabase_url = "sqlite:///keep.db"\n')

        args = argparse.Namespace(
            key="project",
            value="new-project",
            config_path=str(config_file),
        )

        _emit_set(args)
        content = config_file.read_text()
        assert "sqlite:///keep.db" in content
        assert "new-project" in content


class TestRun:
    def test_show_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test run with show command."""
        args = argparse.Namespace(config_command="show", format="text")

        config = TrackerConfig(
            database_url=None,
            project="test",
            suite=None,
            jsonl_path=None,
            config_path=None,
        )

        with mock.patch("pytest_chronicle.cli.config_cmd.get_default_config", return_value=config):
            result = run(args)

        assert result == 0

    def test_set_command(self, tmp_path: Path) -> None:
        """Test run with set command."""
        config_file = tmp_path / ".pytest-chronicle.toml"

        args = argparse.Namespace(
            config_command="set",
            key="project",
            value="run-test",
            config_path=str(config_file),
        )

        result = run(args)
        assert result == 0
        assert config_file.exists()

    def test_unknown_command(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Test run with unknown command returns error."""
        args = argparse.Namespace(config_command="unknown")

        result = run(args)
        assert result == 2

        captured = capsys.readouterr()
        assert "Unknown config command" in captured.err
