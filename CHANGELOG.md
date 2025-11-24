# Changelog

## 0.2.0 - 2025-11-23
- Added repo-level configuration via `.pytest-chronicle.toml` with precedence (CLI > env > config > fallback).
- New `pytest-chronicle init` helper to scaffold config plus an async SQLite database by default.
- New `pytest-chronicle config show|set` commands to inspect or update defaults without retyping flags.
- Default fallback database now lives at `<repo>/.pytest-chronicle/chronicle.db` (async SQLite), and schema creation ensures directories exist.
- Pytest plugin now auto-ingests using repo/env defaults when `--chronicle-db` is omitted; improved coverage for config-driven ingestion.

## 0.2.1 - 2025-11-23
- Plugin defaults to ingesting when any configured/fallback DB is present (no flag needed).
- README streamlined for first-time users; added detailed `docs/guide.md`.

## 0.2.2 - 2025-11-23
- Added `pytest-chronicle query timeline` for colored TTY run-by-run status matrices.
- Docs updated with timeline usage; tests cover JSON output and status rendering.

## 0.2.3 - 2025-11-23
- Added demo script with verified sandbox steps for recording a GIF.

## 0.2.4 - 2025-11-23
- `pytest-chronicle init` now auto-detects project name from pyproject.toml or the current directory and emits guidance on how to change it.
- Docs updated to reflect project auto-detection behavior.

## 0.2.5 - 2025-11-23
- Added `query last-green` to surface the most recent passing run per test.
- Introduced label/tag support (`--label/--labels`) as the preferred replacement for suite; config accepts comma-separated labels.
- Captured pytest invocation string during ingestion; docs updated accordingly.

## 0.1.1 - 2025-11-23
- Added rich `query` CLI (last-red/errors/flipped-green/compare) with pytest-like selectors and JSON/text output.
- Introduced pluggable query backends and SQL backend implementation; documented backend extension path.
- Added safe error-detail output with truncation and optional stdout/stderr inclusion.
- Added pytest `--chronicle-db` flag for seamless ingestion at session end (supports sqlite/postgres URLs).
- Expanded unit coverage for queries and plugin ingestion flag.

## 0.1.0 - 2025-??-??
- Initial published package skeleton (pytest plugin, ingestion, basic CLI).
