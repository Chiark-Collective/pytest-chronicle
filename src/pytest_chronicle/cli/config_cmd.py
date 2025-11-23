from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pytest_chronicle.config import (
    TrackerConfig,
    default_config_path,
    get_default_config,
    load_repo_config,
    write_config,
)


def configure_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("config", help="Inspect or update repo-local pytest-chronicle defaults.")
    sub = parser.add_subparsers(dest="config_command", required=True)

    show = sub.add_parser("show", help="Show the effective configuration (env overrides applied).")
    show.add_argument("--format", choices=("text", "json"), default="text")

    set_cmd = sub.add_parser("set", help="Persist a value to the repo config file.")
    set_cmd.add_argument("key", choices=("database_url", "project", "suite", "jsonl_path"))
    set_cmd.add_argument("value", help="Value to write (use '' to clear).")
    set_cmd.add_argument("--config-path", help="Path to the config file (defaults to repo root).")
    return parser


def _mask(value: str | None) -> str:
    if value is None:
        return ""
    if "@" in value and "://" in value:
        # Avoid leaking credentials in URLs.
        try:
            prefix, rest = value.split("://", 1)
            userinfo, remainder = rest.split("@", 1)
            return f"{prefix}://***@{remainder}"
        except ValueError:
            return value
    return value


def _emit_show(args: argparse.Namespace) -> int:
    cfg = get_default_config()
    payload = {
        "config_path": str(cfg.config_path) if cfg.config_path else None,
        "database_url": cfg.database_url,
        "project": cfg.project,
        "suite": cfg.suite,
        "jsonl_path": cfg.jsonl_path,
    }
    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(f"config: {payload['config_path'] or default_config_path()}")
        print(f"database_url: {_mask(payload['database_url']) or '(not set)'}")
        print(f"project: {payload['project'] or '(not set)'}")
        print(f"suite: {payload['suite'] or '(not set)'}")
        if payload["jsonl_path"]:
            print(f"jsonl_path: {payload['jsonl_path']}")
    return 0


def _emit_set(args: argparse.Namespace) -> int:
    key = args.key
    value = args.value if args.value != "" else None
    path = Path(args.config_path).expanduser().resolve() if args.config_path else default_config_path()
    existing = load_repo_config(path=path)
    updated = TrackerConfig(
        database_url=existing.database_url,
        project=existing.project,
        suite=existing.suite,
        jsonl_path=existing.jsonl_path,
        config_path=path,
    )
    setattr(updated, key, value)
    try:
        written = write_config(updated, path, force=True)
    except Exception as exc:  # pragma: no cover - thin CLI wrapper
        print(f"Failed to write config: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {key} to {written}")
    return 0


def run(args: argparse.Namespace) -> int:
    if args.config_command == "show":
        return _emit_show(args)
    if args.config_command == "set":
        return _emit_set(args)
    print(f"Unknown config command: {args.config_command}", file=sys.stderr)
    return 2
