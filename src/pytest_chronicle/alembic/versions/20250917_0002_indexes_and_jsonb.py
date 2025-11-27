from __future__ import annotations

from alembic import op

revision = "20250917_0002_indexes_and_jsonb"
down_revision = "20250917_0001_init"
branch_labels = None
depends_on = None


def _is_postgres(bind) -> bool:
    try:
        return bind.dialect.name == "postgresql"
    except Exception:
        return False


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE INDEX IF NOT EXISTS ix_test_runs_created_at ON test_runs (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_test_runs_branch ON test_runs (branch)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_test_runs_suite ON test_runs (suite)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_test_cases_status ON test_cases (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_test_cases_run_id ON test_cases (run_id)")

    if _is_postgres(bind):
        for col in ("env", "junit", "ci"):
            op.execute(f"ALTER TABLE test_runs ALTER COLUMN {col} TYPE jsonb USING {col}::jsonb")
        op.execute("CREATE INDEX IF NOT EXISTS ix_test_runs_junit_gin ON test_runs USING gin (junit)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_test_runs_ci_gin ON test_runs USING gin (ci)")


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DROP INDEX IF EXISTS ix_test_cases_run_id")
    op.execute("DROP INDEX IF EXISTS ix_test_cases_status")
    op.execute("DROP INDEX IF EXISTS ix_test_runs_suite")
    op.execute("DROP INDEX IF EXISTS ix_test_runs_branch")
    op.execute("DROP INDEX IF EXISTS ix_test_runs_created_at")

    if _is_postgres(bind):
        op.execute("DROP INDEX IF EXISTS ix_test_runs_junit_gin")
        op.execute("DROP INDEX IF EXISTS ix_test_runs_ci_gin")
        for col in ("env", "junit", "ci"):
            op.execute(f"ALTER TABLE test_runs ALTER COLUMN {col} TYPE text USING {col}::text")
