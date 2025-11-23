# pytest-chronicle

Traceable pytest history: capture results, ingest them into a SQL store (SQLite or Postgres), and answer questions like “when did this test last go red?” or “which commit flipped it green?”.

## What it does
- Pytest plugin emits per-test JSONL records (stdout/stderr/traceback included).
- Ingestion stamps runs with git/CI metadata and writes to SQLite or Postgres.
- CLI queries last failures, error details, flip-to-green commits, and branch/commit diffs with pytest-like selectors.

## Install

```bash
uv pip install pytest-chronicle
```

## Quickstart

```bash
pytest-chronicle init --project my-project --suite pytest          # create config + local sqlite
pytest --chronicle-db sqlite:///./.pytest-chronicle/chronicle.db   # run tests and auto-ingest
pytest-chronicle query last-red --format json --pretty             # ask questions
```

## Common commands
- `pytest-chronicle init` – scaffold `.pytest-chronicle.toml` and an async SQLite DB.
- `pytest-chronicle ingest --jsonl <path>` – ingest JSONL/summary artifacts.
- `pytest-chronicle query last-red|errors|flipped-green|compare` – history lookups (`-k`/`-m` like pytest).
- `pytest-chronicle run <project> -- <pytest args>` – run pytest under `uv`, collect artifacts, optionally ingest.
- `pytest-chronicle backfill` – ingest many summary.json files.
- `pytest-chronicle export-sqlite` / `import-sqlite` – migrate between backends.
- `pytest-chronicle db upgrade` – apply Alembic migrations.
- `pytest-chronicle config show|set` – view or set repo defaults.

## Configuration & defaults
- Precedence: CLI flag `--database-url` > env (`PYTEST_RESULTS_DB_URL`, legacy `TEST_RESULTS_DATABASE_URL` / `SCS_DATABASE_URL`) > `.pytest-chronicle.toml` > fallback SQLite at `<repo>/.pytest-chronicle/chronicle.db` (async).
- Example config:
  ```toml
  [chronicle]
  database_url = "postgresql+asyncpg://user:pass@host/db"
  project = "my-project"
  suite = "pytest"
  ```
- Typical flow: use SQLite for local dev (via `init`); point env or config at Postgres for CI/prod. No other changes needed.

## Pytest plugin (auto ingestion)
- Install the package; the `pytest_chronicle` plugin is auto-discovered.
- If a database is configured via env/config (or fallback SQLite), the plugin will ingest automatically at session end. You can still pass `--chronicle-db <url>` to override, or `--chronicle-no-ingest` to skip.
- Default JSONL path: `.artifacts/test-results/chronicle-results.jsonl` (created automatically).

## More docs
- Detailed guide: `docs/guide.md`
- Backend abstraction: `docs/storage-backends.md`
