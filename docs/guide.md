# pytest-chronicle guide

## Overview
pytest-chronicle captures pytest results, enriches them with git/CI metadata, stores them in SQL (SQLite or Postgres), and offers a CLI to investigate failures over time (last red, error details, flip-to-green commits, branch/commit comparisons).

## Installation

```bash
uv pip install pytest-chronicle
```

Core dependencies: `sqlalchemy`, `sqlmodel`, `aiosqlite`, `asyncpg`, `alembic`. For development/tests use the `dev` extra.

## Configuration

Precedence for the database URL and defaults:
1. CLI flag `--database-url`
2. Env vars: `PYTEST_RESULTS_DB_URL` (or legacy `TEST_RESULTS_DATABASE_URL` / `SCS_DATABASE_URL`)
3. Repo file `.pytest-chronicle.toml`
4. Fallback async SQLite at `<repo>/.pytest-chronicle/chronicle.db`

Config file example:

```toml
[chronicle]
database_url = "postgresql+asyncpg://user:pass@host:5432/dbname"
project = "my-project"
suite = "pytest"
jsonl_path = ".artifacts/test-results/chronicle-results.jsonl"
```

Tips:
- Use SQLite (from `pytest-chronicle init`) for local development.
- Point the config or env at Postgres for CI/prod; no code changes required.
- `PYTEST_CHRONICLE_CONFIG` can point to an alternate config path for monorepos.

## CLI commands

- `init`: create `.pytest-chronicle.toml`; default DB is async SQLite under `.pytest-chronicle/chronicle.db`. `--database-url` overrides; `--no-schema` skips schema creation.
- `config show|set`: inspect or update repo defaults without retyping flags.
- `run <project> -- <pytest args>`: run pytest via `uv run`, write JSONL/JUnit/summary artifacts, and (unless `--skip-ingest`) ingest into the resolved database.
- `ingest --jsonl <path>` or `--summary <path>`: ingest artifacts with optional `--project/--suite/--run-id/--run-key`.
- `query last-red|errors|flipped-green|compare`: rich history lookups. Shared filters: `-k` (pytest keyword expression), `-m` (marks), `--project-like`, `--suite`, `--branch`, `--commit`, `--limit`. Output: `--format text|json`, `--pretty`, `--output <file>`.
  - `last-red`: most recent failing/erroring occurrence per test (with commit, branch, run id).
  - `errors`: latest failure details (message/detail/stdout/stderr; truncated by default, toggle with `--include-stdout/--include-stderr`, `--max-chars`).
  - `flipped-green`: commit where a previously red test most recently turned green (shows previous failing commit).
  - `compare`: latest status per test across branches/commits; `--only-diff` to surface regressions.
- `latest-red`: lightweight “still red” listing (per-test or latest run modes).
- `backfill`: ingest many summary.json artifacts (`--glob` patterns, `--dry-run` to list).
- `export-sqlite` / `import-sqlite`: move data between backends using a portable SQLite file.
- `db`: Alembic driver (`upgrade`, `downgrade`, `current`, `history`, `stamp`, `revision`).

## Pytest plugin

The `pytest_chronicle` plugin is auto-discovered via `pytest11`. Flags:
- `--chronicle-db <url>`: ingest at session end (async URL forms accepted). If omitted, the resolver uses env → config → SQLite fallback.
- `--chronicle-project`, `--chronicle-suite`: override metadata.
- `--chronicle-no-ingest`: keep JSONL export but skip ingestion.

JSONL output defaults to `.artifacts/test-results/chronicle-results.jsonl` when a chronicle DB is set; directories are created automatically.

Example:

```bash
pytest -q --chronicle-db postgresql+asyncpg://user:pass@db/ci --chronicle-project api --chronicle-suite smoke
```

## Typical workflows

- **Local dev (SQLite):**
  ```bash
  pytest-chronicle init --project myproj --suite pytest
  pytest --chronicle-db sqlite:///./.pytest-chronicle/chronicle.db
  pytest-chronicle query last-red -k "flaky" --format json --pretty
  ```

- **CI (Postgres):**
  ```bash
  export PYTEST_RESULTS_DB_URL=postgresql+asyncpg://user:pass@db/ci
  pytest --chronicle-suite ci-smoke --chronicle-project service-a
  pytest-chronicle query compare --branch main --branch feature/foo --only-diff --format json
  ```

## Development & testing

Run the test suite (needs sqlite + asyncpg + alembic extras):

```bash
PYTHONPATH=src uv run --with pytest --with sqlmodel --with sqlalchemy \
  --with aiosqlite --with asyncpg --with alembic pytest -q
```

Build & publish:

```bash
uv build
uv publish --token $PYPI_API_TOKEN
```
