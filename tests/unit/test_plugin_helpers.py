"""Tests for pytest_chronicle.pytest_plugin helper functions."""

from __future__ import annotations

from unittest import mock

import pytest

from pytest_chronicle.pytest_plugin import (
    _cap,
    _resolve_outcome,
    _text,
    _to_async_url,
)


class TestToAsyncUrl:
    def test_converts_postgresql_to_asyncpg(self) -> None:
        """Test converting postgresql:// to asyncpg."""
        result = _to_async_url("postgresql://user:pass@host/db")
        assert result == "postgresql+asyncpg://user:pass@host/db"

    def test_converts_sqlite_to_aiosqlite(self) -> None:
        """Test converting sqlite:/// to aiosqlite."""
        result = _to_async_url("sqlite:///path/to/db.sqlite")
        assert result == "sqlite+aiosqlite:///path/to/db.sqlite"

    def test_preserves_already_async_sqlite(self) -> None:
        """Test preserves already async SQLite URL."""
        url = "sqlite+aiosqlite:///path/to/db.sqlite"
        result = _to_async_url(url)
        assert result == url

    def test_preserves_already_async_postgresql(self) -> None:
        """Test preserves already async PostgreSQL URL."""
        url = "postgresql+asyncpg://user:pass@host/db"
        result = _to_async_url(url)
        assert result == url

    def test_preserves_unknown_scheme(self) -> None:
        """Test preserves unknown URL schemes."""
        url = "mysql://user:pass@host/db"
        result = _to_async_url(url)
        assert result == url


class TestText:
    def test_converts_to_string(self) -> None:
        """Test converting values to string."""
        assert _text("hello") == "hello"
        assert _text(123) == "123"
        assert _text(45.67) == "45.67"

    def test_handles_none(self) -> None:
        """Test None returns empty string."""
        assert _text(None) == ""

    def test_handles_exception(self) -> None:
        """Test handles objects that fail str()."""

        class BadStr:
            def __str__(self):
                raise ValueError("Cannot convert")

        result = _text(BadStr())
        assert result == ""


class TestCap:
    def test_truncates_long_string(self) -> None:
        """Test truncating long strings."""
        text = "x" * 30000
        result = _cap(text, 1000)
        assert len(result) < 30000
        assert "[truncated]" in result

    def test_preserves_short_string(self) -> None:
        """Test short strings are preserved."""
        text = "short"
        result = _cap(text, 1000)
        assert result == text

    def test_handles_empty(self) -> None:
        """Test empty string returns empty."""
        assert _cap("") == ""

    def test_handles_none_like(self) -> None:
        """Test None-like values return empty."""
        assert _cap(None) == ""  # type: ignore


class TestEnsureFunction:
    """Test the _ensure helper function."""

    def test_creates_new_record(self) -> None:
        """Test _ensure creates a new record for unknown nodeid."""
        from pytest_chronicle.pytest_plugin import _ensure

        class MockConfig:
            _results_buffer = {}

        config = MockConfig()
        result = _ensure(config, "test::a")

        assert "test::a" in config._results_buffer
        assert result["nodeid"] == "test::a"
        assert result["outcome"] is None
        assert result["phases"] == {}

    def test_returns_existing_record(self) -> None:
        """Test _ensure returns existing record."""
        from pytest_chronicle.pytest_plugin import _ensure

        class MockConfig:
            _results_buffer = {"test::a": {"nodeid": "test::a", "outcome": "passed"}}

        config = MockConfig()
        result = _ensure(config, "test::a")

        assert result["outcome"] == "passed"


class TestIngestFromJsonl:
    """Test the _ingest_from_jsonl helper function."""

    def test_calls_ingest_async(self, tmp_path) -> None:
        """Test _ingest_from_jsonl calls the async ingest function."""
        from unittest import mock
        from pytest_chronicle.pytest_plugin import _ingest_from_jsonl

        jsonl_path = tmp_path / "results.jsonl"
        jsonl_path.write_text('{"nodeid": "test::a"}\n')

        class MockReporter:
            def __init__(self):
                self.lines = []

            def write_line(self, msg, **kwargs):
                self.lines.append(msg)

        reporter = MockReporter()

        # Mock the ingest module before import
        with mock.patch("pytest_chronicle.ingest.ingest") as mock_ingest:
            async def mock_fn(*args, **kwargs):
                pass

            mock_ingest.return_value = mock_fn()

            _ingest_from_jsonl(
                reporter,
                jsonl_path=jsonl_path,
                database_url="sqlite:///test.db",
                project="proj",
                suite="suite",
                pytest_args="-v",
            )

        # Should have written success message
        assert any("[chronicle]" in line for line in reporter.lines)


class TestResolveOutcome:
    """Test the _resolve_outcome helper for xfail/xpass detection."""

    def test_xfail_skipped_with_wasxfail(self) -> None:
        """Test xfail test (expected failure that failed) is detected."""

        class MockReport:
            outcome = "skipped"
            wasxfail = "expected to fail"

        result = _resolve_outcome(MockReport())
        assert result == "xfailed"

    def test_xpass_passed_with_wasxfail(self) -> None:
        """Test xpass test (expected failure that passed) is detected."""

        class MockReport:
            outcome = "passed"
            wasxfail = "should have failed"

        result = _resolve_outcome(MockReport())
        assert result == "xpassed"

    def test_normal_passed(self) -> None:
        """Test normal passing test is unchanged."""

        class MockReport:
            outcome = "passed"

        result = _resolve_outcome(MockReport())
        assert result == "passed"

    def test_normal_failed(self) -> None:
        """Test normal failing test is unchanged."""

        class MockReport:
            outcome = "failed"

        result = _resolve_outcome(MockReport())
        assert result == "failed"

    def test_normal_skipped(self) -> None:
        """Test normal skipped test (without wasxfail) is unchanged."""

        class MockReport:
            outcome = "skipped"

        result = _resolve_outcome(MockReport())
        assert result == "skipped"

    def test_strict_xpass_is_failed(self) -> None:
        """Test strict xpass (outcome=failed with wasxfail) returns failed.

        When @pytest.mark.xfail(strict=True) passes, pytest sets outcome='failed',
        so we shouldn't special-case it - it's already a proper failure.
        """

        class MockReport:
            outcome = "failed"
            wasxfail = "strict mode"

        result = _resolve_outcome(MockReport())
        assert result == "failed"

    def test_error_outcome(self) -> None:
        """Test error outcome is unchanged."""

        class MockReport:
            outcome = "error"

        result = _resolve_outcome(MockReport())
        assert result == "error"

    def test_wasxfail_empty_string(self) -> None:
        """Test wasxfail as empty string still triggers xfail detection."""

        class MockReport:
            outcome = "skipped"
            wasxfail = ""

        result = _resolve_outcome(MockReport())
        assert result == "xfailed"
