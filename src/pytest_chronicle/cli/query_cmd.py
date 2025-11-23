from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from pytest_chronicle.backends import QueryParams, resolve_backend
from pytest_chronicle.config import resolve_database_url
from pytest_chronicle.ingest import default_database_url


def _parse_common_args(args: argparse.Namespace) -> QueryParams:
    return QueryParams(
        project_like=args.project_like,
        suite=args.suite,
        branches=args.branch or [],
        commits=args.commit or [],
        keyword=args.keyword,
        marks=args.mark,
        limit=args.limit,
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


def _emit(payload: dict[str, Any], args: argparse.Namespace) -> None:
    payload = _to_jsonable(payload)
    if args.format == "json":
        text_out = json.dumps(payload, indent=2 if args.pretty else None)
    else:
        text_out = _render_text(payload)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(text_out + ("\n" if not text_out.endswith("\n") else ""), encoding="utf-8")
        print(f"wrote {out_path}", file=sys.stderr)
    else:
        print(text_out)


def _render_text(payload: dict[str, Any]) -> str:
    kind = payload.get("kind", "")
    items: list[dict[str, Any]] = payload.get("items", [])
    lines: list[str] = []
    if kind in {"last-red", "errors", "flipped-green"}:
        for item in items:
            parts = [item.get("nodeid", ""), f"status={item.get('status', '')}", f"commit={item.get('head_sha', '')}"]
            if item.get("branch"):
                parts.append(f"branch={item.get('branch')}")
            if item.get("created_at"):
                parts.append(f"when={item.get('created_at')}")
            parts.append(f"run={item.get('run_id', '')}")
            if kind == "errors":
                msg = item.get("message") or item.get("detail") or ""
                preview = str(msg).splitlines()[0] if msg else ""
                if preview:
                    parts.append(f"msg={preview}")
            if kind == "flipped-green" and item.get("prev_head_sha"):
                parts.append(f"from={item.get('prev_head_sha')}")
            lines.append(" | ".join(parts))
    elif kind == "compare":
        for item in items:
            parts = [item.get("nodeid", "")]
            for source in item.get("sources", []):
                parts.append(f"{source.get('source')}={source.get('status', '')}@{source.get('head_sha', '')}")
            lines.append(" | ".join(parts))
    else:
        lines.append(json.dumps(payload))
    return "\n".join(lines)


def configure_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    db_parent = argparse.ArgumentParser(add_help=False)
    db_parent.add_argument("--database-url", help="Override database URL.")

    base = argparse.ArgumentParser(add_help=False)
    base.add_argument("--project-like", default="%", help="SQL LIKE filter for project column (default: %).")
    base.add_argument("--suite", help="Optional suite filter.")
    base.add_argument("--branch", action="append", help="Restrict to one or more branches (can repeat).")
    base.add_argument("--commit", action="append", help="Restrict to specific head shas (can repeat).")
    base.add_argument("-k", "--keyword", help="Pytest -k style keyword expression against nodeid/classname/name.")
    base.add_argument("-m", "--mark", help="Simple mark expression matched against run marks.")
    base.add_argument("--limit", type=int, default=50, help="Max number of rows returned (default 50).")

    output = argparse.ArgumentParser(add_help=False)
    output.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    output.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    output.add_argument("--output", help="Optional path to write results instead of stdout.")

    parser = subparsers.add_parser("query", help="Run rich test result queries.")
    sub = parser.add_subparsers(dest="query_command", required=True)

    sub.add_parser(
        "last-red",
        help="Show the most recent failing run per matching test (commit hash included).",
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
        else:
            print(f"Unknown query command: {args.query_command}", file=sys.stderr)
            return 2
    finally:
        backend.close()

    _emit(payload, args)
    return 0
