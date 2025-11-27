"""Tests for pytest_chronicle export_sqlite and import_sqlite modules."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlmodel import SQLModel, Session, create_engine

from pytest_chronicle.export_sqlite import (
    export_database,
    main as export_main,
    normalize_sync_url as export_normalize,
    parse_args as export_parse_args,
)
from pytest_chronicle.import_sqlite import (
    import_database,
    main as import_main,
    normalize_sync_url as import_normalize,
    parse_args as import_parse_args,
)
from pytest_chronicle.models import TestCase, TestRun


def _create_test_db(db_path: Path) -> str:
    """Create a test database with sample data."""
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        run = TestRun(
            id="test-run-1",
            created_at=datetime.now(timezone.utc),
            project="test-project",
            suite="test-suite",
            status="PASS",
            head_sha="abc123",
            code_hash="hash",
            branch="main",
            parent_sha="parent",
            origin_url="https://github.com/test/repo",
            describe="v1.0.0",
            commit_timestamp=datetime.now(timezone.utc).isoformat(),
            is_dirty=False,
            gpu="cpu",
            marks="smoke",
            pytest_args="-v",
            platform="linux",
            python_version="3.12",
            host="localhost",
            tests=2,
            failures=0,
            errors=0,
            skipped=0,
            passed=2,
            time_sec=1.5,
            env={},
            junit={},
            ci={},
            report_dir="",
            run_key="test-run-1-key",
        )
        session.add(run)
        session.add(
            TestCase(
                run_id="test-run-1",
                nodeid="tests/test_a.py::test_one",
                classname="tests/test_a.py",
                name="test_one",
                status="passed",
                time_sec=0.5,
                message="",
                detail="",
                stdout_text="",
                stderr_text="",
            )
        )
        session.add(
            TestCase(
                run_id="test-run-1",
                nodeid="tests/test_a.py::test_two",
                classname="tests/test_a.py",
                name="test_two",
                status="passed",
                time_sec=1.0,
                message="",
                detail="",
                stdout_text="",
                stderr_text="",
            )
        )
        session.commit()

    engine.dispose()
    return url


class TestExportNormalizeSyncUrl:
    def test_converts_asyncpg_to_psycopg2(self) -> None:
        """Test converting asyncpg URL to psycopg2."""
        result = export_normalize("postgresql+asyncpg://user:pass@host/db")
        assert result == "postgresql+psycopg2://user:pass@host/db"

    def test_converts_aiosqlite_to_sqlite(self) -> None:
        """Test converting aiosqlite URL to sqlite."""
        result = export_normalize("sqlite+aiosqlite:///path/to/db")
        assert result == "sqlite:///path/to/db"

    def test_preserves_other_urls(self) -> None:
        """Test other URLs are preserved."""
        result = export_normalize("postgresql://user:pass@host/db")
        assert result == "postgresql://user:pass@host/db"


class TestImportNormalizeSyncUrl:
    def test_converts_asyncpg_to_psycopg2(self) -> None:
        """Test converting asyncpg URL to psycopg2."""
        result = import_normalize("postgresql+asyncpg://user:pass@host/db")
        assert result == "postgresql+psycopg2://user:pass@host/db"

    def test_converts_aiosqlite_to_sqlite(self) -> None:
        """Test converting aiosqlite URL to sqlite."""
        result = import_normalize("sqlite+aiosqlite:///path/to/db")
        assert result == "sqlite:///path/to/db"


class TestExportParseArgs:
    def test_requires_database_url(self) -> None:
        """Test --database-url is required."""
        with pytest.raises(SystemExit):
            export_parse_args(["--out", "/tmp/out.db"])

    def test_requires_out(self) -> None:
        """Test --out is required."""
        with pytest.raises(SystemExit):
            export_parse_args(["--database-url", "sqlite:///test.db"])

    def test_parses_args(self) -> None:
        """Test parsing valid arguments."""
        args = export_parse_args(["--database-url", "sqlite:///test.db", "--out", "/tmp/out.db"])
        assert args.database_url == "sqlite:///test.db"
        assert args.out == "/tmp/out.db"


class TestImportParseArgs:
    def test_requires_sqlite(self) -> None:
        """Test --sqlite is required."""
        with pytest.raises(SystemExit):
            import_parse_args(["--database-url", "sqlite:///test.db"])

    def test_requires_database_url(self) -> None:
        """Test --database-url is required."""
        with pytest.raises(SystemExit):
            import_parse_args(["--sqlite", "/tmp/source.db"])

    def test_parses_args(self) -> None:
        """Test parsing valid arguments."""
        args = import_parse_args(["--sqlite", "/tmp/source.db", "--database-url", "sqlite:///dest.db"])
        assert args.sqlite == "/tmp/source.db"
        assert args.database_url == "sqlite:///dest.db"


class TestExportDatabase:
    def test_exports_all_runs_and_cases(self, tmp_path: Path) -> None:
        """Test exporting database includes all runs and cases."""
        source_db = tmp_path / "source.db"
        dest_db = tmp_path / "dest.db"

        source_url = _create_test_db(source_db)

        count = export_database(source_url, dest_db)
        assert count == 1  # One run exported

        # Verify destination has the data
        dest_engine = create_engine(f"sqlite:///{dest_db}")
        with Session(dest_engine) as session:
            runs = session.query(TestRun).all()
            assert len(runs) == 1
            assert runs[0].id == "test-run-1"

            cases = session.query(TestCase).all()
            assert len(cases) == 2
        dest_engine.dispose()

    def test_creates_destination_directory(self, tmp_path: Path) -> None:
        """Test creates destination directory if missing."""
        source_db = tmp_path / "source.db"
        dest_db = tmp_path / "sub" / "deep" / "dest.db"

        source_url = _create_test_db(source_db)

        export_database(source_url, dest_db)
        assert dest_db.exists()

    def test_handles_async_url(self, tmp_path: Path) -> None:
        """Test handles aiosqlite URL."""
        source_db = tmp_path / "source.db"
        dest_db = tmp_path / "dest.db"

        _create_test_db(source_db)
        async_url = f"sqlite+aiosqlite:///{source_db}"

        count = export_database(async_url, dest_db)
        assert count == 1


class TestImportDatabase:
    def test_imports_runs_and_cases(self, tmp_path: Path) -> None:
        """Test importing database includes all runs and cases."""
        source_db = tmp_path / "source.db"
        dest_db = tmp_path / "dest.db"

        _create_test_db(source_db)

        # Create empty destination
        dest_url = f"sqlite:///{dest_db}"
        dest_engine = create_engine(dest_url)
        SQLModel.metadata.create_all(dest_engine)
        dest_engine.dispose()

        count = import_database(source_db, dest_url)
        assert count == 1

        # Verify destination has the data
        dest_engine = create_engine(dest_url)
        with Session(dest_engine) as session:
            runs = session.query(TestRun).all()
            assert len(runs) == 1

            cases = session.query(TestCase).all()
            assert len(cases) == 2
        dest_engine.dispose()

    def test_skips_existing_runs(self, tmp_path: Path) -> None:
        """Test skips runs that already exist (by run_key)."""
        source_db = tmp_path / "source.db"
        dest_db = tmp_path / "dest.db"

        _create_test_db(source_db)

        # Create destination with same run
        _create_test_db(dest_db)
        dest_url = f"sqlite:///{dest_db}"

        count = import_database(source_db, dest_url)
        assert count == 0  # No new runs imported

    def test_handles_async_destination_url(self, tmp_path: Path) -> None:
        """Test handles aiosqlite destination URL."""
        source_db = tmp_path / "source.db"
        dest_db = tmp_path / "dest.db"

        _create_test_db(source_db)

        async_url = f"sqlite+aiosqlite:///{dest_db}"
        count = import_database(source_db, async_url)
        assert count == 1


class TestExportMain:
    def test_main_success(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Test main function success."""
        source_db = tmp_path / "source.db"
        dest_db = tmp_path / "dest.db"

        source_url = _create_test_db(source_db)

        result = export_main(["--database-url", source_url, "--out", str(dest_db)])
        assert result == 0

        captured = capsys.readouterr()
        assert "Exported 1 runs" in captured.out


class TestImportMain:
    def test_main_success(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Test main function success."""
        source_db = tmp_path / "source.db"
        dest_db = tmp_path / "dest.db"

        _create_test_db(source_db)
        dest_url = f"sqlite:///{dest_db}"

        result = import_main(["--sqlite", str(source_db), "--database-url", dest_url])
        assert result == 0

        captured = capsys.readouterr()
        assert "Imported 1 runs" in captured.out
