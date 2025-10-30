from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20250917_0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "test_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project", sa.String(), nullable=False),
        sa.Column("suite", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("head_sha", sa.String(), nullable=False),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("branch", sa.String(), nullable=False),
        sa.Column("parent_sha", sa.String(), nullable=False),
        sa.Column("origin_url", sa.String(), nullable=False),
        sa.Column("describe", sa.String(), nullable=False),
        sa.Column("commit_timestamp", sa.String(), nullable=False),
        sa.Column("is_dirty", sa.Boolean(), nullable=False),
        sa.Column("gpu", sa.String(), nullable=False),
        sa.Column("marks", sa.String(), nullable=False),
        sa.Column("pytest_args", sa.String(), nullable=False),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("python_version", sa.String(), nullable=False),
        sa.Column("host", sa.String(), nullable=False),
        sa.Column("tests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("time_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("env", sa.Text(), nullable=True),
        sa.Column("junit", sa.Text(), nullable=True),
        sa.Column("ci", sa.Text(), nullable=True),
        sa.Column("report_dir", sa.String(), nullable=False, server_default=""),
        sa.Column("run_key", sa.String(), nullable=False, unique=True),
    )

    op.create_table(
        "test_cases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(), nullable=False, index=True),
        sa.Column("nodeid", sa.String(), nullable=False),
        sa.Column("classname", sa.String(), nullable=False, server_default=""),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("time_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("message", sa.String(), nullable=False, server_default=""),
        sa.Column("detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("stdout_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("stderr_text", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("test_cases")
    op.drop_table("test_runs")
