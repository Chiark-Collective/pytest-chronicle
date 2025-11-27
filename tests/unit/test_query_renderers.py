"""Tests for pytest_chronicle.cli.query_cmd rendering functions."""

from __future__ import annotations

import argparse
import io
from datetime import datetime, timezone

import pytest
from rich.console import Console

from pytest_chronicle.cli.query_cmd import (
    _build_console,
    _format_rate,
    _format_seconds,
    _format_time_styled,
    _maybe_trim,
    _parse_pytest_select,
    _parse_time_arg,
    _prepare_errors,
    _render_compare,
    _render_slowest_table,
    _render_stats_table,
    _render_status_table,
    _render_text,
    _render_timeline,
    _shorten_sha,
    _status_text,
    _to_jsonable,
)


class TestParseTimeArg:
    def test_parses_hours(self) -> None:
        """Test parsing hour duration."""
        result = _parse_time_arg("5h")
        assert result is not None
        now = datetime.now(timezone.utc)
        # Should be approximately 5 hours ago
        delta = now - result
        assert 4.9 * 3600 < delta.total_seconds() < 5.1 * 3600

    def test_parses_minutes(self) -> None:
        """Test parsing minute duration."""
        result = _parse_time_arg("30m")
        assert result is not None
        now = datetime.now(timezone.utc)
        delta = now - result
        assert 29 * 60 < delta.total_seconds() < 31 * 60

    def test_parses_days(self) -> None:
        """Test parsing day duration."""
        result = _parse_time_arg("2d")
        assert result is not None
        now = datetime.now(timezone.utc)
        delta = now - result
        assert 1.9 * 86400 < delta.total_seconds() < 2.1 * 86400

    def test_parses_iso_timestamp(self) -> None:
        """Test parsing ISO timestamp."""
        result = _parse_time_arg("2024-01-15T10:30:00")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_returns_none_for_invalid(self) -> None:
        """Test returns None for invalid input."""
        assert _parse_time_arg(None) is None
        assert _parse_time_arg("") is None
        assert _parse_time_arg("invalid") is None

    def test_handles_float_duration(self) -> None:
        """Test parsing float durations like 1.5h."""
        result = _parse_time_arg("1.5h")
        assert result is not None


class TestParsePytestSelect:
    def test_parses_keyword(self) -> None:
        """Test parsing -k option."""
        tests, keyword, mark = _parse_pytest_select("-k mytest")
        assert keyword == "mytest"

    def test_parses_mark(self) -> None:
        """Test parsing -m option."""
        tests, keyword, mark = _parse_pytest_select("-m slow")
        assert mark == "slow"

    def test_parses_selectors(self) -> None:
        """Test parsing test selectors."""
        tests, keyword, mark = _parse_pytest_select("tests/test_a.py tests/test_b.py")
        assert "tests/test_a.py" in tests
        assert "tests/test_b.py" in tests

    def test_parses_combined(self) -> None:
        """Test parsing combined options."""
        tests, keyword, mark = _parse_pytest_select("-m slow -k fast tests/test_x.py")
        assert keyword == "fast"
        assert mark == "slow"
        assert "tests/test_x.py" in tests

    def test_handles_double_dash(self) -> None:
        """Test parsing with -- separator."""
        tests, keyword, mark = _parse_pytest_select("-k expr -- tests/a.py tests/b.py")
        assert keyword == "expr"
        assert "tests/a.py" in tests
        assert "tests/b.py" in tests

    def test_handles_empty(self) -> None:
        """Test parsing empty input."""
        tests, keyword, mark = _parse_pytest_select(None)
        assert tests == []
        assert keyword is None
        assert mark is None


class TestMaybeTrim:
    def test_trims_long_text(self) -> None:
        """Test trimming long text."""
        result = _maybe_trim("x" * 100, 50)
        assert len(result) <= 50
        assert "truncated" in result

    def test_preserves_short_text(self) -> None:
        """Test short text is preserved."""
        result = _maybe_trim("short", 100)
        assert result == "short"

    def test_handles_none(self) -> None:
        """Test None is preserved."""
        assert _maybe_trim(None, 100) is None

    def test_zero_max_disables(self) -> None:
        """Test zero max_chars disables trimming."""
        text = "x" * 1000
        result = _maybe_trim(text, 0)
        assert result == text


class TestPrepareErrors:
    def test_trims_message_and_detail(self) -> None:
        """Test message and detail are trimmed."""
        items = [{"message": "x" * 500, "detail": "y" * 500}]
        args = argparse.Namespace(max_chars=100, include_stdout=False, include_stderr=False)

        result = _prepare_errors(items, args)
        assert len(result[0]["message"]) <= 100
        assert len(result[0]["detail"]) <= 100

    def test_includes_stdout_when_flagged(self) -> None:
        """Test stdout included when flag set."""
        items = [{"message": "", "detail": "", "stdout_text": "stdout content"}]
        args = argparse.Namespace(max_chars=0, include_stdout=True, include_stderr=False)

        result = _prepare_errors(items, args)
        assert "stdout_text" in result[0]
        assert result[0]["stdout_text"] == "stdout content"

    def test_excludes_stdout_by_default(self) -> None:
        """Test stdout excluded by default."""
        items = [{"message": "", "detail": "", "stdout_text": "stdout content"}]
        args = argparse.Namespace(max_chars=0, include_stdout=False, include_stderr=False)

        result = _prepare_errors(items, args)
        assert "stdout_text" not in result[0]


class TestToJsonable:
    def test_converts_datetime(self) -> None:
        """Test datetime conversion to ISO string."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _to_jsonable(dt)
        assert "2024-01-15" in result

    def test_handles_nested_dict(self) -> None:
        """Test nested dict conversion."""
        data = {"nested": {"dt": datetime(2024, 1, 1, tzinfo=timezone.utc)}}
        result = _to_jsonable(data)
        assert "2024-01-01" in result["nested"]["dt"]

    def test_handles_list(self) -> None:
        """Test list conversion."""
        data = [datetime(2024, 1, 1, tzinfo=timezone.utc)]
        result = _to_jsonable(data)
        assert "2024-01-01" in result[0]


class TestShortenSha:
    def test_shortens_sha(self) -> None:
        """Test SHA shortening."""
        assert _shorten_sha("abcdef1234567890") == "abcdef1234"

    def test_handles_short_sha(self) -> None:
        """Test short SHA is preserved."""
        assert _shorten_sha("abc") == "abc"

    def test_handles_none(self) -> None:
        """Test None returns empty string."""
        assert _shorten_sha(None) == ""


class TestStatusText:
    def test_passed_green(self) -> None:
        """Test passed status is green."""
        result = _status_text("passed")
        assert "green" in str(result.style)

    def test_failed_red(self) -> None:
        """Test failed status is red."""
        result = _status_text("failed")
        assert "red" in str(result.style)

    def test_skipped_yellow(self) -> None:
        """Test skipped status is yellow."""
        result = _status_text("skipped")
        assert "yellow" in str(result.style)

    def test_glyph_mode(self) -> None:
        """Test glyph mode returns single character."""
        result = _status_text("passed", glyph=True)
        assert result.plain == "P"

        result = _status_text("failed", glyph=True)
        assert result.plain == "F"


class TestFormatSeconds:
    def test_seconds(self) -> None:
        """Test formatting seconds."""
        assert _format_seconds(2.5) == "2.50s"

    def test_milliseconds(self) -> None:
        """Test formatting milliseconds."""
        assert _format_seconds(0.123) == "123ms"

    def test_microseconds(self) -> None:
        """Test formatting microseconds."""
        assert _format_seconds(0.000456) == "456μs"

    def test_invalid_returns_empty(self) -> None:
        """Test invalid input returns empty."""
        assert _format_seconds(None) == ""
        assert _format_seconds("invalid") == ""


class TestFormatRate:
    def test_formats_percentage(self) -> None:
        """Test percentage formatting."""
        assert _format_rate(42.567) == "42.6%"

    def test_invalid_returns_empty(self) -> None:
        """Test invalid input returns empty."""
        assert _format_rate(None) == ""
        assert _format_rate("invalid") == ""


class TestBuildConsole:
    def test_creates_console(self) -> None:
        """Test console creation."""
        args = argparse.Namespace(no_color=False)
        console = _build_console(args)
        assert isinstance(console, Console)

    def test_no_color_flag(self) -> None:
        """Test no_color flag disables color."""
        args = argparse.Namespace(no_color=True)
        console = _build_console(args)
        assert console.no_color is True

    def test_to_file_disables_color(self) -> None:
        """Test to_file disables color."""
        args = argparse.Namespace(no_color=False)
        console = _build_console(args, to_file=True)
        assert console.no_color is True


class TestRenderStatusTable:
    def test_renders_basic_table(self) -> None:
        """Test basic status table rendering."""
        items = [
            {
                "nodeid": "test::a",
                "status": "passed",
                "head_sha": "abc123def456",
                "time_sec": 0.5,
                "created_at": "2024-01-15",
                "run_id": "run1",
            }
        ]
        args = argparse.Namespace(no_color=True, show_marks=False)
        buffer = io.StringIO()
        console = Console(file=buffer, no_color=True)

        _render_status_table("last-green", items, args, console)
        output = buffer.getvalue()
        assert "test::a" in output
        assert "passed" in output

    def test_renders_with_marks(self) -> None:
        """Test table rendering with marks."""
        items = [
            {
                "nodeid": "test::a",
                "status": "passed",
                "head_sha": "abc123",
                "time_sec": 0.5,
                "created_at": "2024-01-15",
                "run_id": "run1",
                "marks": "slow,smoke",
            }
        ]
        args = argparse.Namespace(no_color=True, show_marks=True)
        buffer = io.StringIO()
        console = Console(file=buffer, no_color=True)

        _render_status_table("last-green", items, args, console)
        output = buffer.getvalue()
        assert "slow,smoke" in output


class TestRenderCompare:
    def test_renders_comparison(self) -> None:
        """Test comparison table rendering."""
        items = [
            {
                "nodeid": "test::a",
                "sources": [
                    {"source": "branch:main", "status": "passed", "head_sha": "abc", "time_sec": 0.1},
                    {"source": "branch:dev", "status": "failed", "head_sha": "def", "time_sec": 0.2},
                ],
            }
        ]
        buffer = io.StringIO()
        console = Console(file=buffer, no_color=True)

        _render_compare(items, console)
        output = buffer.getvalue()
        assert "test::a" in output
        assert "main" in output
        assert "dev" in output

    def test_handles_empty(self) -> None:
        """Test empty results message."""
        buffer = io.StringIO()
        console = Console(file=buffer, no_color=True)

        _render_compare([], console)
        output = buffer.getvalue()
        assert "No results" in output


class TestRenderTimeline:
    def test_renders_timeline(self) -> None:
        """Test timeline rendering."""
        payload = {
            "runs": [
                {"head_sha": "sha1", "branch": "main", "created_at": "2024-01-15"},
                {"head_sha": "sha2", "branch": "main", "created_at": "2024-01-14"},
            ],
            "items": [
                {"nodeid": "test::a", "statuses": ["passed", "failed"], "times": [0.1, 0.2]},
            ],
        }
        args = argparse.Namespace(no_color=True, compact=False, show_times=False)
        buffer = io.StringIO()
        console = Console(file=buffer, no_color=True)

        _render_timeline(payload, args, console)
        output = buffer.getvalue()
        assert "test::a" in output

    def test_shows_times_when_flagged(self) -> None:
        """Test timeline shows times when flagged."""
        payload = {
            "runs": [{"head_sha": "sha1", "branch": "main", "created_at": "2024-01-15"}],
            "items": [{"nodeid": "test::a", "statuses": ["passed"], "times": [1.5]}],
        }
        args = argparse.Namespace(no_color=True, compact=False, show_times=True)
        buffer = io.StringIO()
        console = Console(file=buffer, no_color=True)

        _render_timeline(payload, args, console)
        output = buffer.getvalue()
        assert "1.50s" in output

    def test_handles_no_runs(self) -> None:
        """Test handles empty runs."""
        payload = {"runs": [], "items": []}
        args = argparse.Namespace(no_color=True, compact=False, show_times=False)
        buffer = io.StringIO()
        console = Console(file=buffer, no_color=True)

        _render_timeline(payload, args, console)
        output = buffer.getvalue()
        assert "No runs" in output


class TestRenderSlowestTable:
    def test_renders_slowest(self) -> None:
        """Test slowest table rendering."""
        items = [
            {
                "nodeid": "test::slow",
                "status": "passed",
                "time_sec": 5.5,
                "head_sha": "abc123",
                "created_at": "2024-01-15",
                "run_id": "run1",
            }
        ]
        args = argparse.Namespace(no_color=True, show_marks=False)
        buffer = io.StringIO()
        console = Console(file=buffer, no_color=True)

        _render_slowest_table(items, args, console)
        output = buffer.getvalue()
        assert "test::slow" in output
        assert "5.50s" in output

    def test_handles_empty(self) -> None:
        """Test handles empty results."""
        args = argparse.Namespace(no_color=True, show_marks=False)
        buffer = io.StringIO()
        console = Console(file=buffer, no_color=True)

        _render_slowest_table([], args, console)
        output = buffer.getvalue()
        assert "No results" in output


class TestRenderStatsTable:
    def test_renders_stats(self) -> None:
        """Test stats table rendering."""
        items = [
            {
                "nodeid": "test::flaky",
                "total_runs": 10,
                "passes": 7,
                "failures": 3,
                "skips": 0,
                "failure_rate": 30.0,
                "avg_time_sec": 0.5,
                "max_time_sec": 1.2,
            }
        ]
        buffer = io.StringIO()
        console = Console(file=buffer, no_color=True)

        _render_stats_table(items, console)
        output = buffer.getvalue()
        assert "test::flaky" in output
        assert "30.0%" in output
        assert "10" in output  # total runs

    def test_handles_empty(self) -> None:
        """Test handles empty results."""
        buffer = io.StringIO()
        console = Console(file=buffer, no_color=True)

        _render_stats_table([], console)
        output = buffer.getvalue()
        assert "No results" in output


class TestRenderText:
    def test_dispatches_to_correct_renderer(self) -> None:
        """Test _render_text dispatches to correct renderer."""
        args = argparse.Namespace(no_color=True, show_marks=False)
        buffer = io.StringIO()
        console = Console(file=buffer, no_color=True)

        # Test last-red
        payload = {"kind": "last-red", "items": []}
        _render_text(payload, args, console)

        # Test slowest
        payload = {"kind": "slowest", "items": []}
        _render_text(payload, args, console)

        # Test stats
        payload = {"kind": "stats", "items": []}
        _render_text(payload, args, console)

        # Test unknown (falls back to JSON)
        payload = {"kind": "unknown", "items": []}
        _render_text(payload, args, console)
