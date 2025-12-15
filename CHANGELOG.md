# Changelog

## 0.4.6 - 2025-12-15
- Removed legacy `latest-red` command; use `query last-red` instead.

## 0.4.5 - 2025-12-15
- Added first-class support for pytest xfail/xpass statuses.
- Plugin detects `wasxfail` attribute and records `xfailed` (expected failure) and `xpassed` (unexpected pass) outcomes.
- Timeline shows `x` (dim) for xfailed and `!` (cyan) for xpassed.
- Stats table conditionally shows `xF` and `xP` columns when xfail/xpass data exists.
- `flipped_green` query now includes xfailed→passed/xpassed transitions.
- Comprehensive test coverage for xfail/xpass detection, rendering, and queries.

## 0.3.0 - 2025-11-24
- Added rich text output for `pytest-chronicle query` (colored tables, timelines; `--no-color` and JSON remain).
- Added pytest-style selectors (positionals and `--pytest-select`) so last-red/last-green/errors/compare respect multiple matched nodeids; selectors normalize backslashes and allow substring matching.
- Surfaced per-test runtime (`time_sec`) across query outputs (JSON/text/compare); timeline/compare retain status-only view.
- Docs updated for selectors, runtimes, and output options; added unit coverage for selectors and runtime presence.

## 0.3.1 - 2025-11-24
- Mark missing/unknown statuses as `?` in timeline/compare text output and fill timeline gaps accordingly.
- Tests cover timeline gaps and compare missing-source behavior; docs mention the `?` marker.

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

## 0.2.6 - 2025-11-23
- Added label filters and `--since-days` to query commands.
- Tests cover label/time filtering; docs/README mention the new options.

## 0.1.1 - 2025-11-23
- Added rich `query` CLI (last-red/errors/flipped-green/compare) with pytest-like selectors and JSON/text output.
- Introduced pluggable query backends and SQL backend implementation; documented backend extension path.
- Added safe error-detail output with truncation and optional stdout/stderr inclusion.
- Added pytest `--chronicle-db` flag for seamless ingestion at session end (supports sqlite/postgres URLs).
- Expanded unit coverage for queries and plugin ingestion flag.

## 0.1.0 - 2025-??-??
- Initial published package skeleton (pytest plugin, ingestion, basic CLI).
