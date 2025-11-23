# Storage backend abstraction (notes)

## Why

- Teams want to keep pytest history in different stores (SQLite on a laptop, Postgres in CI, maybe DuckDB/BigQuery later).
- Query features (last red, flipped green, branch compares) depend on backend-specific SQL today. A narrow API lets new backends plug in without rewriting the CLI.

## Minimal API surface

Defined in `pytest_chronicle.backends` as `QueryBackend` + `QueryParams`:

- `last_red(params) -> list[dict]`: most recent failing/erroring run per nodeid.
- `errors(params) -> list[dict]`: same as `last_red` plus message/detail/stdout/stderr.
- `flipped_green(params) -> list[dict]`: most recent transition from red to green per nodeid.
- `compare(params, branches, commits) -> list[dict]`: latest status per node across requested sources.
- `close()`: cleanup/dispose resources.

Current resolver (`resolve_backend`) routes every URL to the SQLAlchemy implementation (`SqlQueryBackend`). Additional backends register by extending the resolver (scheme map, entry points, or a small registry).

The CLI resolves the database URL from CLI flags → environment → `.pytest-chronicle.toml` → an async SQLite fallback at `<repo>/.pytest-chronicle/chronicle.db` before constructing a backend. This keeps default, file-based storage working without explicit flags while still allowing alternative backends.

## Extending beyond SQL

Backends are responsible for implementing the above methods using their native query language:

- **SQLite/Postgres**: already supported via the shared SQL backend.
- SQLite URLs may be provided as `sqlite:///path.db` (sync) or `sqlite+aiosqlite:///path.db`; the resolver normalizes the async form for query usage.
- **DuckDB/Parquet**: implement with DuckDB SQL queries over Parquet/JSONL exports.
- **HTTP/Service**: translate calls into REST/GraphQL; return the same shape as the protocol.
- **BigQuery/Snowflake**: mirror the SQL backend but swap the connection + dialect-specific syntax (window functions, LIMIT syntax, etc.).

Considerations for new backends:

- Window functions and ordering are required (`ROW_NUMBER`, `LAG`). If missing, emulate in the backend.
- Schema alignment: backends should expose fields equivalent to `test_runs` and `test_cases`, or provide a compatible view.
- Performance knobs: pagination (`limit`), projections (omit heavy fields unless asked), and optional stdout/stderr streaming for large payloads.

## Future tightening

- Promote `QueryParams` to a `TypedDict`/`dataclass` shared with ingestion to reuse selection logic.
- Add an ingestion/persistence interface beside `QueryBackend` so storage choices are end-to-end, not just for queries.
- Allow backend selection via `PYTEST_CHRONICLE_BACKEND=duckdb://...` with pluggable entry points.
- Ship contract tests that any backend must pass, using a small fixture dataset.

For now the SQL backend is the reference implementation; the resolver hook plus documented protocol should keep future backends small and localized.
