from __future__ import annotations

import argparse
import io
import json
import shlex
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any

from pytest_chronicle.backends import QueryParams, resolve_backend
from pytest_chronicle.config import resolve_database_url
from pytest_chronicle.ingest import default_database_url


from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text


def _parse_time_arg(value: str | None) -> datetime | None:
    if not value:
        return None
    val = value.strip()
    now = datetime.now(timezone.utc)
    # duration like 5h, 30m, 2d
    if val[-1] in {"h", "m", "d"} and val[:-1].replace(".", "", 1).isdigit():
        num = float(val[:-1])
        if val.endswith("h"):
            return now - timedelta(hours=num)
        if val.endswith("m"):
            return now - timedelta(minutes=num)
        if val.endswith("d"):
            return now - timedelta(days=num)
    # ISO8601 timestamp
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return None


def _parse_pytest_select(arg: str | None) -> tuple[list[str], str | None, str | None]:
    if not arg:
        return [], None, None
    tests: list[str] = []
    keyword: str | None = None
    mark: str | None = None
    tokens = shlex.split(arg)
    it = iter(tokens)
    for tok in it:
        if tok == "--":
            tests.extend(list(it))
            break
        if tok in ("-k", "--keyword"):
            keyword = next(it, None)
            continue
        if tok in ("-m", "--markexpr"):
            mark = next(it, None)
            continue
        if tok.startswith("-"):
            # Unknown option; ignore and keep parsing.
            continue
        tests.append(tok)
    return tests, keyword, mark


def _parse_common_args(args: argparse.Namespace) -> QueryParams:
    since = _parse_time_arg(getattr(args, "since", None))
    until = _parse_time_arg(getattr(args, "until", None))
    pytest_tests, pytest_keyword, pytest_mark = _parse_pytest_select(getattr(args, "pytest_select", None))
    selectors = list(getattr(args, "tests", None) or [])
    selectors.extend(pytest_tests)
    statuses = getattr(args, "status", None) or []
    return QueryParams(
        project_like=args.project_like,
        suite=args.suite,
        labels=getattr(args, "labels", None),
        branches=args.branch or [],
        commits=args.commit or [],
        keyword=args.keyword or pytest_keyword,
        marks=args.mark or pytest_mark,
        limit=args.limit,
        selectors=selectors,
        since=since,
        until=until,
        statuses=statuses,
    )


def _maybe_trim(value: Any, max_chars: int | None) -> Any:
    if value is None:
        return value
    text = str(value)
    if max_chars is not None and max_chars > 0 and len(text) > max_chars:
        suffix = "... (truncated)"
        keep = max(max_chars - len(suffix), 0)
        return text[:keep] + suffix
    return text


def _prepare_errors(items: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    max_chars: int | None = args.max_chars
    verbosity = getattr(args, "verbosity", 0)
    # Verbosity levels: -v=1 full traceback, -vv=2 +stdout, -vvv=3 +stderr
    include_stdout = getattr(args, "include_stdout", False) or verbosity >= 2
    include_stderr = getattr(args, "include_stderr", False) or verbosity >= 3
    # Don't truncate in verbose mode
    if verbosity >= 1:
        max_chars = None

    prepared: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        row["message"] = _maybe_trim(row.get("message"), max_chars)
        row["detail"] = _maybe_trim(row.get("detail"), max_chars)
        if include_stdout:
            row["stdout_text"] = _maybe_trim(row.get("stdout_text"), max_chars)
        else:
            row.pop("stdout_text", None)
        if include_stderr:
            row["stderr_text"] = _maybe_trim(row.get("stderr_text"), max_chars)
        else:
            row.pop("stderr_text", None)
        prepared.append(row)
    return prepared


def _to_jsonable(obj: Any) -> Any:
    from datetime import datetime

    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_jsonable(v) for v in obj]
    return obj


def _shorten_sha(value: str | None, length: int = 10) -> str:
    if not value:
        return ""
    return value[:length]


def _shorten_nodeid(nodeid: str, max_width: int | None = None) -> str:
    """Shorten a test nodeid for display.

    Strips directory path to keep just filename::class::method.
    If still too long and max_width is set, uses middle truncation with '...'.

    Examples:
        demo/demo-workspace/test_api.py::TestAuth::test_login
        -> test_api.py::TestAuth::test_login

        test_api.py::TestAuthEndpoints::test_login_very_long_name
        -> test_api.py::...::test_login_very_long_name (with max_width)
    """
    if not nodeid:
        return ""

    # Split into path and test parts (path/to/file.py::Class::method)
    if "::" in nodeid:
        path_part, rest = nodeid.split("::", 1)
        # Strip directory path, keep just filename
        filename = path_part.rsplit("/", 1)[-1]
        result = f"{filename}::{rest}"
    else:
        # No :: separator, just strip directory
        result = nodeid.rsplit("/", 1)[-1]

    # Apply max_width truncation if needed
    if max_width and len(result) > max_width:
        # Try to preserve filename and test method, truncate class name in middle
        if "::" in result:
            parts = result.split("::")
            if len(parts) >= 2:
                # Keep filename and last part (test method), truncate middle
                filename = parts[0]
                test_method = parts[-1]
                # Calculate available space
                min_chars = len(filename) + len(test_method) + 6  # for "::" + "..." + "::"
                if min_chars < max_width and len(parts) > 2:
                    # Can fit filename + ... + method
                    result = f"{filename}::...::{test_method}"
                elif len(result) > max_width:
                    # Need more aggressive truncation
                    keep = max_width - 3  # for "..."
                    half = keep // 2
                    result = result[:half] + "..." + result[-(keep - half):]
        else:
            # Simple middle truncation
            keep = max_width - 3
            half = keep // 2
            result = result[:half] + "..." + result[-(keep - half):]

    return result


def _shorten_uuid(value: str | None) -> str:
    """Shorten a UUID to just the first segment (8 chars before the first dash)."""
    if not value:
        return ""
    # UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    # Return just the first segment
    return value.split("-")[0] if "-" in value else value[:8]


def _status_text(status: str | None, *, glyph: bool = False) -> Text:
    # Mapping: (glyph_char, color)
    # xfailed: expected failure that failed as expected - dim, not concerning
    # xpassed: expected failure that passed unexpectedly - cyan, needs attention
    mapping = {
        "passed": ("P", "green"),
        "failed": ("F", "red"),
        "error": ("E", "magenta"),
        "skipped": ("S", "yellow"),
        "xfailed": ("x", "dim"),
        "xpassed": ("!", "cyan"),
        "?": ("?", "bright_black"),
    }
    if not status:
        return Text("?" if glyph else "", style="bright_black")
    key = str(status).lower()
    glyph_char, style = mapping.get(key, ("?" if glyph else status, "bright_black"))
    label = glyph_char if glyph else status
    return Text(label, style=style)


def _build_console(args: argparse.Namespace, *, to_file: bool = False, file: Any | None = None, record: bool = False) -> Console:
    disable_color = getattr(args, "no_color", False) or to_file
    return Console(
        file=file,
        no_color=disable_color,
        record=record,
    )


def _format_seconds(value: Any) -> str:
    """Format seconds as a plain string with smart units."""
    try:
        num = float(value)
    except Exception:
        return ""
    if num >= 1:
        return f"{num:.2f}s"
    if num >= 0.001:
        return f"{num * 1000:.0f}ms"
    return f"{num * 1_000_000:.0f}μs"


# Thresholds for slow test highlighting (in seconds)
SLOW_THRESHOLD = 1.0  # Tests >= 1s are "slow" (yellow)
VERY_SLOW_THRESHOLD = 5.0  # Tests >= 5s are "very slow" (bold orange/red)


def _format_timestamp(value: Any, *, compact: bool = False) -> str:
    """Format a timestamp, truncating microseconds for display.

    Args:
        value: Timestamp value to format
        compact: If True, split date and time with newline for narrower display
    """
    if not value:
        return ""
    # Truncate to YYYY-MM-DD HH:MM:SS (19 chars)
    ts = str(value)[:19]
    if compact and len(ts) >= 11:
        # Split into "YYYY-MM-DD\nHH:MM:SS" (10 chars wide instead of 19)
        return ts[:10] + "\n" + ts[11:]
    return ts


def _format_time_styled(value: Any) -> Text:
    """Format seconds as a Rich Text object with smart units and slow test highlighting."""
    try:
        num = float(value)
    except Exception:
        return Text("")

    # Determine the display string with appropriate units
    if num >= 1:
        display = f"{num:.2f}s"
    elif num >= 0.001:
        display = f"{num * 1000:.0f}ms"
    else:
        display = f"{num * 1_000_000:.0f}μs"

    # Apply styling based on duration
    if num >= VERY_SLOW_THRESHOLD:
        return Text(display, style="bold bright_red")
    elif num >= SLOW_THRESHOLD:
        return Text(display, style="bold yellow")
    else:
        return Text(display)


def _render_status_table(kind: str, items: list[dict[str, Any]], args: argparse.Namespace, console: Console) -> None:
    has_branch = any(item.get("branch") for item in items)
    show_marks = getattr(args, "show_marks", False)
    has_marks = show_marks and any(item.get("marks") for item in items)
    is_errors = kind == "errors"

    table = Table(box=box.SIMPLE_HEAVY, expand=True)

    # Get display flags
    show_commit = not getattr(args, "no_commit", False)
    show_run = not getattr(args, "no_run", False)

    if is_errors:
        # Minimal columns for errors: Test, When, Message
        # Skip Status (always failed), Commit, Time, Branch, Run to save space
        # Use -v for full details
        table.add_column("Test", overflow="ellipsis", no_wrap=True, min_width=20, max_width=50)
        table.add_column("When", no_wrap=False, max_width=11)
        table.add_column("Message", overflow="fold")
    else:
        # Use ellipsis with min_width to prevent Test from being squished at narrow widths
        table.add_column("Test", overflow="ellipsis", no_wrap=True, min_width=20, max_width=60)
        table.add_column("Status", no_wrap=True)
        if show_commit:
            table.add_column("Commit", no_wrap=True, style="cyan")
        table.add_column("Time", no_wrap=True, justify="right")
        if has_branch:
            table.add_column("Branch", no_wrap=True)
        if has_marks:
            table.add_column("Marks", no_wrap=True, style="dim")
        table.add_column("When", no_wrap=True)
        if show_run:
            table.add_column("Run", no_wrap=True)
        if kind == "flipped-green":
            table.add_column("From", no_wrap=True, style="dim")

    for item in items:
        row: list[Any] = [_shorten_nodeid(item.get("nodeid", ""))]

        if is_errors:
            row.append(_format_timestamp(item.get("created_at"), compact=True))
            msg = item.get("message") or item.get("detail") or ""
            preview = msg.splitlines()[0] if msg else ""
            row.append(preview)
        else:
            status_cell = _status_text(item.get("status"))
            time_cell = _format_time_styled(item.get("time_sec"))
            row.append(status_cell)
            if show_commit:
                row.append(_shorten_sha(item.get("head_sha")))
            row.append(time_cell)
            if has_branch:
                row.append(item.get("branch") or "")
            if has_marks:
                row.append(item.get("marks") or "")
            row.append(_format_timestamp(item.get("created_at")))
            if show_run:
                row.append(_shorten_uuid(item.get("run_id")))
            if kind == "flipped-green":
                row.append(_shorten_sha(item.get("prev_head_sha")))

        table.add_row(*row)

    console.print(table)


def _render_compare(items: list[dict[str, Any]], console: Console) -> None:
    if not items:
        console.print("No results.")
        return

    columns: list[str] = []
    for item in items:
        for src in item.get("sources", []):
            name = src.get("source")
            if name and name not in columns:
                columns.append(name)

    table = Table(box=box.SIMPLE_HEAVY, expand=True)
    table.add_column("Test", overflow="fold")
    for col in columns:
        table.add_column(col, no_wrap=True, justify="center")

    for item in items:
        row: list[Any] = [_shorten_nodeid(item.get("nodeid", ""))]
        mapping = {src.get("source"): src for src in item.get("sources", [])}
        for col in columns:
            src = mapping.get(col)
            if not src:
                row.append(Text("?", style="bright_black"))
                continue
            status_cell = _status_text(src.get("status"))
            sha = _shorten_sha(src.get("head_sha"))
            if sha:
                status_cell.append("\n")
                status_cell.append(sha, style="dim")
            time_styled = _format_time_styled(src.get("time_sec"))
            if time_styled.plain:
                status_cell.append("\n")
                status_cell.append_text(time_styled)
            row.append(status_cell)
        table.add_row(*row)

    console.print(table)


def _render_timeline(payload: dict[str, Any], args: argparse.Namespace, console: Console) -> None:
    runs: list[dict[str, Any]] = payload.get("runs", [])
    items: list[dict[str, Any]] = payload.get("items", [])
    if not runs:
        console.print("No runs found.")
        return

    compact = getattr(args, "compact", False)
    show_times = getattr(args, "show_times", False)
    table = Table(
        box=box.SIMPLE_HEAVY,
        expand=not compact,
        padding=(0, 0 if compact else 1),
        show_lines=False,
    )
    table.add_column("Test", overflow="ellipsis", no_wrap=True)
    for run in runs:
        label = _shorten_sha(run.get("head_sha"))
        branch = run.get("branch")
        if branch:
            label = f"{label}@{branch}"
        table.add_column(label, justify="center", no_wrap=True)

    for item in items:
        statuses = item.get("statuses", [])
        times = item.get("times", [])
        cells: list[Text] = []
        for idx in range(len(runs)):
            status = statuses[idx] if idx < len(statuses) else None
            cell = _status_text(status, glyph=True)
            if show_times and idx < len(times) and times[idx] is not None:
                time_styled = _format_time_styled(times[idx])
                if time_styled.plain:
                    cell.append(" ")
                    cell.append_text(time_styled)
            cells.append(cell)
        table.add_row(_shorten_nodeid(item.get("nodeid", "")), *cells)

    created_cells = [str(r.get("created_at") or "") for r in runs]
    if any(created_cells):
        table.caption = f"When: {' | '.join(created_cells)}"

    console.print(table)


def _render_slowest_table(items: list[dict[str, Any]], args: argparse.Namespace, console: Console) -> None:
    """Render tests sorted by execution time."""
    if not items:
        console.print("No results.")
        return

    has_branch = any(item.get("branch") for item in items)
    show_marks = getattr(args, "show_marks", False)
    has_marks = show_marks and any(item.get("marks") for item in items)
    show_commit = not getattr(args, "no_commit", False)

    table = Table(box=box.SIMPLE_HEAVY, expand=True)
    # Use ellipsis with min/max width for Test to prevent squishing
    table.add_column("Test", overflow="ellipsis", no_wrap=True, min_width=20, max_width=50)
    table.add_column("Status", no_wrap=True)
    table.add_column("Time", no_wrap=True, justify="right")
    if show_commit:
        table.add_column("Commit", no_wrap=True, style="cyan")
    if has_branch:
        table.add_column("Branch", no_wrap=True)
    if has_marks:
        table.add_column("Marks", no_wrap=True, style="dim")
    table.add_column("When", no_wrap=True)

    for item in items:
        status_cell = _status_text(item.get("status"))
        time_cell = _format_time_styled(item.get("time_sec"))
        row: list[Any] = [
            _shorten_nodeid(item.get("nodeid", "")),
            status_cell,
            time_cell,
        ]
        if show_commit:
            row.append(_shorten_sha(item.get("head_sha")))
        if has_branch:
            row.append(item.get("branch") or "")
        if has_marks:
            row.append(item.get("marks") or "")
        row.append(_format_timestamp(item.get("created_at")))
        table.add_row(*row)

    console.print(table)


def _format_rate(value: Any) -> str:
    """Format a percentage value."""
    try:
        num = float(value)
    except Exception:
        return ""
    return f"{num:.1f}%"


def _render_stats_table(items: list[dict[str, Any]], console: Console) -> None:
    """Render test statistics with failure rates and timing."""
    if not items:
        console.print("No results.")
        return

    # Check if any xfail/xpass data exists to decide whether to show those columns
    has_xfail = any(item.get("xfails", 0) for item in items)
    has_xpass = any(item.get("xpasses", 0) for item in items)

    table = Table(box=box.SIMPLE_HEAVY, expand=True)
    table.add_column("Test", overflow="fold", ratio=2)
    table.add_column("Runs", no_wrap=True, justify="right")
    table.add_column("Pass", no_wrap=True, justify="right", style="green")
    table.add_column("Fail", no_wrap=True, justify="right", style="red")
    table.add_column("Skip", no_wrap=True, justify="right", style="yellow")
    if has_xfail:
        table.add_column("xF", no_wrap=True, justify="right", style="dim")
    if has_xpass:
        table.add_column("xP", no_wrap=True, justify="right", style="cyan")
    table.add_column("Fail%", no_wrap=True, justify="right")
    table.add_column("Avg", no_wrap=True, justify="right")
    table.add_column("Max", no_wrap=True, justify="right")

    for item in items:
        failure_rate = item.get("failure_rate", 0)
        # Color failure rate based on severity
        if failure_rate >= 50:
            rate_style = "bold red"
        elif failure_rate >= 20:
            rate_style = "red"
        elif failure_rate >= 5:
            rate_style = "yellow"
        else:
            rate_style = "green"

        rate_text = Text(_format_rate(failure_rate), style=rate_style)

        row: list[Any] = [
            _shorten_nodeid(item.get("nodeid", "")),
            str(item.get("total_runs", 0)),
            str(item.get("passes", 0)),
            str(item.get("failures", 0)),
            str(item.get("skips", 0)),
        ]
        if has_xfail:
            row.append(str(item.get("xfails", 0)))
        if has_xpass:
            row.append(str(item.get("xpasses", 0)))
        row.extend([
            rate_text,
            _format_time_styled(item.get("avg_time_sec")),
            _format_time_styled(item.get("max_time_sec")),
        ])
        table.add_row(*row)

    console.print(table)


def _render_errors_verbose(items: list[dict[str, Any]], args: argparse.Namespace, console: Console) -> None:
    """Render errors in pytest-like verbose format."""
    if not items:
        console.print("No errors found.")
        return

    verbosity = getattr(args, "verbosity", 0)
    total = len(items)

    # Short summary header like pytest
    console.print(Rule(f"[bold red]FAILURES[/] ({total} test{'s' if total != 1 else ''})", style="red"))
    console.print()

    for i, item in enumerate(items):
        nodeid = _shorten_nodeid(item.get("nodeid", ""))
        status = item.get("status", "failed")
        message = item.get("message", "")
        detail = item.get("detail", "")
        stdout_text = item.get("stdout_text", "")
        stderr_text = item.get("stderr_text", "")
        time_sec = item.get("time_sec")
        head_sha = item.get("head_sha", "")
        branch = item.get("branch", "")
        created_at = item.get("created_at", "")

        # Test header like pytest: _____ test_name _____
        console.print(Rule(f"[bold]{nodeid}[/]", style="red", characters="_"))
        console.print()

        # Metadata line
        commit_str = _shorten_sha(head_sha)
        time_text = _format_time_styled(time_sec) if time_sec is not None else Text("")
        meta_text = Text()
        if commit_str:
            meta_text.append("commit: ")
            meta_text.append(commit_str, style="cyan")
            meta_text.append("  ")
        if branch:
            meta_text.append("branch: ")
            meta_text.append(branch, style="green")
            meta_text.append("  ")
        if time_text.plain:
            meta_text.append("time: ")
            meta_text.append_text(time_text)
            meta_text.append("  ")
        if created_at:
            meta_text.append("when: ")
            meta_text.append(str(created_at)[:19], style="dim")
        if meta_text.plain.strip():
            console.print(meta_text)
            console.print()

        # Error detail (traceback) - format like pytest
        if detail:
            for line in detail.splitlines():
                if line.startswith("E ") or line.startswith("E\t"):
                    # Error assertion lines in red
                    console.print(f"[red]{line}[/]")
                elif line.strip().startswith(">"):
                    # Source line indicator
                    console.print(f"[bold]{line}[/]")
                else:
                    # Regular traceback lines
                    console.print(f"[dim]{line}[/]")
            console.print()
        elif message:
            console.print(f"[red]E   {message}[/]")
            console.print()

        # Captured stdout (verbosity >= 2 or --include-stdout)
        if stdout_text:
            console.print(Panel(
                stdout_text.rstrip(),
                title="[dim]Captured stdout call[/]",
                border_style="dim",
                padding=(0, 1),
            ))
            console.print()

        # Captured stderr (verbosity >= 3 or --include-stderr)
        if stderr_text:
            console.print(Panel(
                stderr_text.rstrip(),
                title="[dim]Captured stderr call[/]",
                border_style="dim",
                padding=(0, 1),
            ))
            console.print()

        # Separator between tests
        if i < total - 1:
            console.print()

    # Short results summary like pytest
    console.print()
    console.print(Rule(style="red", characters="="))
    console.print(f"[bold red]{total} failed[/]")


def _render_text(payload: dict[str, Any], args: argparse.Namespace, console: Console) -> None:
    kind = payload.get("kind", "")
    items: list[dict[str, Any]] = payload.get("items", [])
    # Use verbose renderer for errors with -v flag
    if kind == "errors" and getattr(args, "verbosity", 0) >= 1:
        _render_errors_verbose(items, args, console)
    elif kind in {"last-red", "last-green", "errors", "flipped-green"}:
        _render_status_table(kind, items, args, console)
    elif kind == "compare":
        _render_compare(items, console)
    elif kind == "timeline":
        _render_timeline(payload, args, console)
    elif kind == "slowest":
        _render_slowest_table(items, args, console)
    elif kind == "stats":
        _render_stats_table(items, console)
    else:
        console.print(json.dumps(payload, indent=2))


def _emit(payload: dict[str, Any], args: argparse.Namespace) -> None:
    payload = _to_jsonable(payload)
    if args.format == "json":
        text_out = json.dumps(payload, indent=2 if args.pretty else None)
        if args.output:
            out_path = Path(args.output)
            if text_out and not text_out.endswith("\n"):
                text_out += "\n"
            out_path.write_text(text_out, encoding="utf-8")
            print(f"wrote {out_path}", file=sys.stderr)
        else:
            print(text_out)
        return

    to_file = bool(args.output)

    buffer = io.StringIO() if to_file else None
    console = _build_console(args, to_file=to_file, file=buffer, record=to_file)
    _render_text(payload, args, console)

    if args.output:
        text_out = buffer.getvalue() if buffer else ""
        out_path = Path(args.output)
        if text_out and not text_out.endswith("\n"):
            text_out += "\n"
        out_path.write_text(text_out, encoding="utf-8")
        print(f"wrote {out_path}", file=sys.stderr)
    elif buffer:
        print(buffer.getvalue(), end="")


def configure_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    db_parent = argparse.ArgumentParser(add_help=False)
    db_parent.add_argument("--database-url", help="Override database URL.")

    base = argparse.ArgumentParser(add_help=False)
    base.add_argument("--project-like", default="%", help="SQL LIKE filter for project column (default: %%).")
    base.add_argument("--suite", help="Optional suite/label filter (deprecated, use --labels).")
    base.add_argument("--label", "--labels", dest="labels", help="Comma-separated label filter.")
    base.add_argument("--branch", action="append", help="Restrict to one or more branches (can repeat).")
    base.add_argument("--commit", action="append", help="Restrict to specific head shas (can repeat).")
    base.add_argument("-k", "--keyword", help="Pytest -k style keyword expression against nodeid/classname/name.")
    base.add_argument("-m", "--mark", help="Simple mark expression matched against run marks.")
    base.add_argument(
        "--pytest-select",
        help="Pytest-style selectors string (e.g. \"-m 'slow and gpu' -k expr tests/test_file.py\"). "
        "Parsed best-effort into -k/-m/nodeid selectors.",
    )
    base.add_argument("--limit", type=int, default=50, help="Max number of rows returned (default 50).")
    base.add_argument("--since", help="Only include runs after this time (duration like 5h/2d or ISO timestamp).")
    base.add_argument("--until", help="Only include runs before this time (duration like 1d or ISO timestamp).")
    base.add_argument(
        "tests",
        nargs="*",
        help="Optional pytest-style nodeid selectors (e.g. tests/test_mod.py::TestClass::test_case).",
    )

    output = argparse.ArgumentParser(add_help=False)
    output.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    output.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    output.add_argument("--output", help="Optional path to write results instead of stdout.")
    output.add_argument("--no-color", action="store_true", help="Disable ANSI color and styling in output.")
    output.add_argument("--show-marks", action="store_true", help="Show test marks/labels in output.")
    output.add_argument("--no-run", action="store_true", help="Hide the Run ID column in output.")
    output.add_argument("--no-commit", action="store_true", help="Hide the Commit column in output.")

    parser = subparsers.add_parser("query", help="Run rich test result queries.")
    sub = parser.add_subparsers(dest="query_command", required=True)

    sub.add_parser(
        "last-red",
        help="Show the most recent failing run per matching test (commit hash included).",
        parents=[base, output, db_parent],
    )
    sub.add_parser(
        "last-green",
        help="Show the most recent passing run per matching test (commit hash included).",
        parents=[base, output, db_parent],
    )

    errors = sub.add_parser(
        "errors",
        help="Show error details for the latest failing occurrence of each matching test.",
        parents=[base, output, db_parent],
    )
    errors.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbosity",
        help="Verbose output: -v shows full traceback, -vv adds stdout, -vvv adds stderr. Like pytest output.",
    )
    errors.add_argument("--include-stdout", action="store_true", help="Include stdout snippets in results.")
    errors.add_argument("--include-stderr", action="store_true", help="Include stderr snippets in results.")
    errors.add_argument(
        "--max-chars",
        type=int,
        default=400,
        help="Truncate message/detail/stdout/stderr to this many characters (default 400). Use 0 to disable.",
    )

    sub.add_parser(
        "flipped-green",
        help="Show the commit where a previously failing test most recently turned green.",
        parents=[base, output, db_parent],
    )

    compare = sub.add_parser(
        "compare",
        help="Compare latest test status across branches or commits.",
        parents=[base, output, db_parent],
    )
    compare.add_argument(
        "--only-diff",
        action="store_true",
        help="Only include tests whose status differs across the requested sources.",
    )

    timeline = sub.add_parser(
        "timeline",
        help="Visual timeline of recent runs for matching tests.",
        parents=[base, output, db_parent],
    )
    timeline.add_argument("--runs", type=int, default=15, help="Number of most recent runs to display (columns).")
    timeline.add_argument("--max-tests", type=int, default=30, help="Limit number of test rows displayed.")
    timeline.add_argument("--compact", action="store_true", help="Compact output (no padding).")
    timeline.add_argument("-t", "--show-times", action="store_true", help="Show execution times alongside status glyphs.")

    slowest = sub.add_parser(
        "slowest",
        help="Show tests ordered by execution time (slowest first).",
        parents=[base, output, db_parent],
    )
    slowest.add_argument(
        "--status",
        action="append",
        choices=["passed", "failed", "error", "skipped"],
        help="Filter by test status (can repeat for multiple statuses).",
    )

    stats = sub.add_parser(
        "stats",
        help="Show test statistics including failure rates and timing.",
        parents=[base, output, db_parent],
    )
    stats.add_argument(
        "--sort-by",
        choices=["failure-rate", "total-runs", "avg-time", "max-time"],
        default="failure-rate",
        help="Sort results by this metric (default: %(default)s).",
    )
    stats.add_argument(
        "--min-runs",
        type=int,
        default=1,
        help="Only show tests with at least this many runs (default: %(default)s).",
    )

    return parser


def _resolve_db_url(args: argparse.Namespace) -> str:
    return args.database_url or resolve_database_url() or default_database_url()


def run(args: argparse.Namespace) -> int:
    db_url = _resolve_db_url(args)
    backend = resolve_backend(db_url)
    params = _parse_common_args(args)
    payload: dict[str, Any]

    try:
        if args.query_command == "last-red":
            payload = {"kind": "last-red", "items": backend.last_red(params)}
        elif args.query_command == "last-green":
            payload = {"kind": "last-green", "items": backend.last_green(params)}
        elif args.query_command == "errors":
            items = backend.errors(params)
            items = _prepare_errors(items, args)
            payload = {"kind": "errors", "items": items}
        elif args.query_command == "flipped-green":
            payload = {"kind": "flipped-green", "items": backend.flipped_green(params)}
        elif args.query_command == "compare":
            branches = args.branch or []
            commits = args.commit or []
            if len(branches) + len(commits) < 2:
                print("compare requires at least two branches/commits", file=sys.stderr)
                return 2
            items = backend.compare(params, branches, commits)
            if getattr(args, "only_diff", False):
                items = [
                    item
                    for item in items
                    if len({src.get("status") for src in item.get("sources", [])}) > 1
                ]
            payload = {"kind": "compare", "items": items}
        elif args.query_command == "timeline":
            payload = backend.timeline(params, runs=args.runs, max_tests=args.max_tests)
        elif args.query_command == "slowest":
            payload = {"kind": "slowest", "items": backend.slowest(params)}
        elif args.query_command == "stats":
            sort_by = getattr(args, "sort_by", "failure-rate")
            items = backend.stats(params, sort_by=sort_by)
            min_runs = getattr(args, "min_runs", 1)
            if min_runs > 1:
                items = [i for i in items if i.get("total_runs", 0) >= min_runs]
            payload = {"kind": "stats", "items": items}
        else:
            print(f"Unknown query command: {args.query_command}", file=sys.stderr)
            return 2
    finally:
        backend.close()

    _emit(payload, args)
    return 0
