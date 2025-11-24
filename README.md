# pytest-chronicle

Searchable git-aware pytest history with a lean CLI and easy storage backends: capture results, ingest into SQLite or Postgres, and answer “when did this test last go red?” or “which commit flipped it green?”.

## What it does

Install from PyPI and configure (`pytest-chronicle init`).

Running `pytest` now: 

- Emits per-test records (result/stdout/stderr/traceback) 
- Persists test result records to SQLite / Postgres (or implement your own storage backend) with:
    - git/CI metadata
    - parent pytest run parameters
    - timestamps
    - user-defined labels





## Install

```bash
pip install pytest-chronicle
```

## Quickstart

```bash
pytest-chronicle init  # create config + local sqlite
pytest -q                                                           # auto-ingests using config/env/fallback SQLite
pytest-chronicle query last-red --format json --pretty             # ask questions
```

## Common commands
- `pytest-chronicle init` – scaffold `.pytest-chronicle.toml` and an async SQLite DB.
- `pytest-chronicle ingest --jsonl <path>` – ingest JSONL/summary artifacts.
- `pytest-chronicle query last-red|errors|flipped-green|compare` – history lookups (`-k`/`-m` like pytest).
- `pytest-chronicle query timeline` – colored TTY timeline of recent runs for matching tests.
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
  suite = "ci-smoke,linux"   # labels/tags (comma-separated)
  ```
- Typical flow: use SQLite for local dev (via `init`); point env or config at Postgres for CI/prod. No other changes needed.
- If you skip `--project` during `init`, it is auto-detected from `pyproject.toml` (or the current folder name); the CLI tells you how to change it later.

## Pytest plugin (auto ingestion)
- Install the package; the `pytest_chronicle` plugin is auto-discovered.
- If a database is configured via env/config (or fallback SQLite), the plugin will ingest automatically at session end. You can still pass `--chronicle-db <url>` to override, or `--chronicle-no-ingest` to skip.
- Default JSONL path: `.artifacts/test-results/chronicle-results.jsonl` (created automatically).

## More docs
- Detailed guide: `docs/guide.md`
- Backend abstraction: `docs/storage-backends.md`
