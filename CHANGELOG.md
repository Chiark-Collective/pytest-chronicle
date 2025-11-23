# Changelog

## 0.1.1 - 2025-11-23
- Added rich `query` CLI (last-red/errors/flipped-green/compare) with pytest-like selectors and JSON/text output.
- Introduced pluggable query backends and SQL backend implementation; documented backend extension path.
- Added safe error-detail output with truncation and optional stdout/stderr inclusion.
- Added pytest `--chronicle-db` flag for seamless ingestion at session end (supports sqlite/postgres URLs).
- Expanded unit coverage for queries and plugin ingestion flag.

## 0.1.0 - 2025-??-??
- Initial published package skeleton (pytest plugin, ingestion, basic CLI).
