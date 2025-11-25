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
    include_stdout = getattr(args, "include_stdout", False)
    include_stderr = getattr(args, "include_stderr", False)

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


def _status_text(status: str | None, *, glyph: bool = False) -> Text:
    mapping = {
        "passed": ("P", "green"),
        "failed": ("F", "red"),
        "error": ("E", "magenta"),
        "skipped": ("S", "yellow"),
    }
    if not status:
        return Text("", style="bright_black")
    key = str(status).lower()
    glyph_char, style = mapping.get(key, ("." if glyph else status, "bright_black"))
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
    try:
        num = float(value)
    except Exception:
        return ""
    if num >= 1:
        return f"{num:.2f}s"
    return f"{num * 1000:.0f}ms"


def _render_status_table(kind: str, items: list[dict[str, Any]], console: Console) -> None:
    has_branch = any(item.get("branch") for item in items)
    table = Table(box=box.SIMPLE_HEAVY, expand=True)
    table.add_column("Test", overflow="fold")
    table.add_column("Status", no_wrap=True)
    table.add_column("Commit", no_wrap=True, style="cyan")
    table.add_column("Time", no_wrap=True, justify="right")
    if has_branch:
        table.add_column("Branch", no_wrap=True)
    table.add_column("When", no_wrap=True)
    table.add_column("Run", no_wrap=True)
    if kind == "errors":
        table.add_column("Message", overflow="fold")
    elif kind == "flipped-green":
        table.add_column("From", no_wrap=True, style="dim")

    for item in items:
        status_cell = _status_text(item.get("status"))
        commit_cell = _shorten_sha(item.get("head_sha"))
        time_cell = _format_seconds(item.get("time_sec"))
        row: list[Any] = [
            item.get("nodeid", ""),
            status_cell,
            commit_cell,
            time_cell,
        ]
        if has_branch:
            row.append(item.get("branch") or "")
        row.append(str(item.get("created_at") or ""))
        row.append(str(item.get("run_id") or ""))

        if kind == "errors":
            msg = item.get("message") or item.get("detail") or ""
            preview = msg.splitlines()[0] if msg else ""
            row.append(preview)
        elif kind == "flipped-green":
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
        row: list[Any] = [item.get("nodeid", "")]
        mapping = {src.get("source"): src for src in item.get("sources", [])}
        for col in columns:
            src = mapping.get(col)
            if not src:
                row.append("")
                continue
            status_cell = _status_text(src.get("status"))
            sha = _shorten_sha(src.get("head_sha"))
            if sha:
                status_cell.append("\n")
                status_cell.append(sha, style="dim")
            time_cell = _format_seconds(src.get("time_sec"))
            if time_cell:
                status_cell.append("\n")
                status_cell.append(time_cell, style="bright_black")
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
    table = Table(
        box=box.SIMPLE_HEAVY,
        expand=not compact,
        padding=(0, 0 if compact else 1),
        show_lines=False,
    )
    table.add_column("Test", overflow="fold")
    for run in runs:
        label = _shorten_sha(run.get("head_sha"))
        branch = run.get("branch")
        if branch:
            label = f"{label}@{branch}"
        table.add_column(label, justify="center", no_wrap=True)

    for item in items:
        statuses = item.get("statuses", [])
        cells: list[Text] = []
        for idx in range(len(runs)):
            status = statuses[idx] if idx < len(statuses) else None
            cells.append(_status_text(status, glyph=True))
        table.add_row(item.get("nodeid", ""), *cells)

    created_cells = [str(r.get("created_at") or "") for r in runs]
    if any(created_cells):
        table.caption = f"When: {' | '.join(created_cells)}"

    console.print(table)


def _render_text(payload: dict[str, Any], args: argparse.Namespace, console: Console) -> None:
    kind = payload.get("kind", "")
    items: list[dict[str, Any]] = payload.get("items", [])
    if kind in {"last-red", "last-green", "errors", "flipped-green"}:
        _render_status_table(kind, items, console)
    elif kind == "compare":
        _render_compare(items, console)
    elif kind == "timeline":
        _render_timeline(payload, args, console)
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
    base.add_argument("--project-like", default="%", help="SQL LIKE filter for project column (default: %).")
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
        else:
            print(f"Unknown query command: {args.query_command}", file=sys.stderr)
            return 2
    finally:
        backend.close()

    _emit(payload, args)
    return 0
