# Changelog

## 0.2.0 - 2025-11-23
- Added repo-level configuration via `.pytest-chronicle.toml` with precedence (CLI > env > config > fallback).
- New `pytest-chronicle init` helper to scaffold config plus an async SQLite database by default.
- New `pytest-chronicle config show|set` commands to inspect or update defaults without retyping flags.
- Default fallback database now lives at `<repo>/.pytest-chronicle/chronicle.db` (async SQLite), and schema creation ensures directories exist.
- Pytest plugin now auto-ingests using repo/env defaults when `--chronicle-db` is omitted; improved coverage for config-driven ingestion.

## 0.1.1 - 2025-11-23
- Added rich `query` CLI (last-red/errors/flipped-green/compare) with pytest-like selectors and JSON/text output.
- Introduced pluggable query backends and SQL backend implementation; documented backend extension path.
- Added safe error-detail output with truncation and optional stdout/stderr inclusion.
- Added pytest `--chronicle-db` flag for seamless ingestion at session end (supports sqlite/postgres URLs).
- Expanded unit coverage for queries and plugin ingestion flag.

## 0.1.0 - 2025-??-??
- Initial published package skeleton (pytest plugin, ingestion, basic CLI).
