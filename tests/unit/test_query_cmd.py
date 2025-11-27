from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlmodel import SQLModel, Session, create_engine

from pytest_chronicle.cli.__main__ import main as cli_main
from pytest_chronicle.models import TestCase, TestRun


def _insert_run(
    engine,
    *,
    run_id: str,
    nodeid: str,
    status: str,
    head_sha: str,
    branch: str,
    created_at: datetime,
    marks: str = "smoke",
    suite: str = "suite",
    message: str = "boom",
    detail: str = "traceback",
    stdout: str = "stdout",
    stderr: str = "stderr",
) -> None:
    with Session(engine) as session:
        run_status = "PASS" if status == "passed" else "FAIL"
        run = TestRun(
            id=run_id,
            created_at=created_at,
            project="proj",
            suite=suite,
            status=run_status,
            head_sha=head_sha,
            code_hash="hash",
            branch=branch,
            parent_sha="",
            origin_url="",
            describe="",
            commit_timestamp=created_at.isoformat(),
            is_dirty=False,
            gpu="cpu",
            marks=marks,
            pytest_args="-k smoke",
            platform="linux",
            python_version="3.12",
            host="localhost",
            tests=1,
            failures=1 if status == "failed" else 0,
            errors=1 if status == "error" else 0,
            skipped=0,
            passed=1 if status == "passed" else 0,
            time_sec=0.1,
            env={},
            junit={},
            ci={},
            report_dir="",
            run_key=f"{run_id}-key",
        )
        session.add(run)
        session.add(
            TestCase(
                run_id=run_id,
                nodeid=nodeid,
                classname=nodeid.split("::")[0],
                name=nodeid.split("::")[-1],
                status=status,
                time_sec=0.1,
                message=message if status != "passed" else "",
                detail=detail if status != "passed" else "",
                stdout_text=stdout if status != "passed" else "",
                stderr_text=stderr if status != "passed" else "",
            )
        )
        session.commit()


def _make_db(tmp_path: Path) -> str:
    db_path = tmp_path / "db.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    _insert_run(
        engine,
        run_id="r1",
        nodeid="pkg/test_sample.py::test_flaky",
        status="failed",
        head_sha="deadbeef",
        branch="main",
        created_at=now - timedelta(hours=2),
    )
    _insert_run(
        engine,
        run_id="r2",
        nodeid="pkg/test_sample.py::test_flaky",
        status="passed",
        head_sha="cafebabe",
        branch="main",
        created_at=now - timedelta(hours=1),
    )
    _insert_run(
        engine,
        run_id="r3",
        nodeid="pkg/test_other.py::test_other",
        status="failed",
        head_sha="a1b2c3d4",
        branch="feature/x",
        created_at=now - timedelta(hours=3),
        marks="slow",
    )
    _insert_run(
        engine,
        run_id="r4",
        nodeid="pkg/test_sample.py::test_flaky",
        status="failed",
        head_sha="f3f3f3",
        branch="feature/x",
        created_at=now - timedelta(hours=2, minutes=30),
    )
    return f"sqlite+aiosqlite:///{db_path}"


def _make_timeline_db(tmp_path: Path) -> tuple[str, list[str]]:
    db_path = tmp_path / "timeline.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    run_ids: list[str] = []
    for idx, status in enumerate(["failed", "passed", "error", "passed"]):
        run_id = f"rt{idx}"
        run_ids.append(run_id)
        _insert_run(
            engine,
            run_id=run_id,
            nodeid="pkg/test_timeline.py::test_timeline",
            status=status,
            head_sha=f"sha{idx}",
            branch="main" if idx % 2 == 0 else "dev",
            created_at=now - timedelta(minutes=idx),
            marks="labels",
        )
    return f"sqlite+aiosqlite:///{db_path}", run_ids


def _make_timeline_with_gap(tmp_path: Path) -> str:
    db_path = tmp_path / "timeline_gap.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    _insert_run(
        engine,
        run_id="rg1",
        nodeid="pkg/test_gap.py::test_gap",
        status="failed",
        head_sha="sha1",
        branch="main",
        created_at=now - timedelta(minutes=2),
    )

    # Add a run with no matching test cases (e.g., filtered pytest run).
    with Session(engine) as session:
        session.add(
            TestRun(
                id="rg2",
                created_at=now - timedelta(minutes=1),
                project="proj",
                suite="suite",
                status="PASS",
                head_sha="sha2",
                code_hash="hash",
                branch="main",
                parent_sha="",
                origin_url="",
                describe="",
                commit_timestamp=now.isoformat(),
                is_dirty=False,
                gpu="cpu",
                marks="smoke",
                pytest_args="-k smoke",
                platform="linux",
                python_version="3.12",
                host="localhost",
                tests=0,
                failures=0,
                errors=0,
                skipped=0,
                passed=0,
                time_sec=0.0,
                env={},
                junit={},
                ci={},
                report_dir="",
                run_key="rg2-key",
            )
        )
        session.commit()

    return f"sqlite+aiosqlite:///{db_path}"


def _make_label_db(tmp_path: Path) -> str:
    db_path = tmp_path / "labels.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    _insert_run(
        engine,
        run_id="r-label1",
        nodeid="pkg/test_lab.py::test_a",
        status="passed",
        head_sha="aa",
        branch="main",
        created_at=now - timedelta(days=1),
        marks="smoke",
        suite="smoke",
        detail="",
        message="",
        stdout="",
        stderr="",
    )
    _insert_run(
        engine,
        run_id="r-label2",
        nodeid="pkg/test_lab.py::test_a",
        status="passed",
        head_sha="bb",
        branch="main",
        created_at=now - timedelta(days=10),
        marks="regression",
        suite="regression",
        detail="",
        message="",
        stdout="",
        stderr="",
    )
    return f"sqlite+aiosqlite:///{db_path}"


def test_query_last_red_and_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = _make_db(tmp_path)

    exit_code = cli_main([
        "query",
        "last-red",
        "--database-url",
        db_url,
        "--project-like",
        "%",
        "--format",
        "json",
    ])
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["kind"] == "last-red"
    item = data["items"][0]
    assert item["head_sha"] == "deadbeef"
    assert item["time_sec"] == pytest.approx(0.1)

    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "last-green",
        "--database-url",
        db_url,
        "--project-like",
        "%",
        "--format",
        "json",
    ])
    assert exit_code == 0
    green = json.loads(capsys.readouterr().out)
    assert green["kind"] == "last-green"
    assert any(it["status"] == "passed" for it in green["items"])

    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "errors",
        "--database-url",
        db_url,
        "--project-like",
        "%",
        "--format",
        "json",
    ])
    assert exit_code == 0
    errors = json.loads(capsys.readouterr().out)["items"]
    assert errors[0]["message"] == "boom"


def test_query_flipped_green(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = _make_db(tmp_path)

    exit_code = cli_main([
        "query",
        "flipped-green",
        "--database-url",
        db_url,
        "--project-like",
        "%",
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["items"][0]["head_sha"] == "cafebabe"


def test_query_compare_branches(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = _make_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "compare",
        "--database-url",
        db_url,
        "--branch",
        "main",
        "--branch",
        "feature/x",
        "--format",
        "json",
        "--only-diff",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["items"], "Expected at least one comparison row"
    sources = payload["items"][0]["sources"]
    statuses = {s["source"]: s["status"] for s in sources}
    assert statuses["branch:main"] == "passed"
    assert statuses["branch:feature/x"] == "failed"
    assert all("time_sec" in s for s in sources)


def test_compare_marks_missing_source_with_unknown(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Only one branch provided, so the other branch column should be missing/unknown.
    db_url = _make_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "compare",
        "--database-url",
        db_url,
        "--branch",
        "main",
        "--branch",
        "nonexistent",
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["items"], "Expected comparison rows"
    first = payload["items"][0]
    sources = {s["source"]: s for s in first["sources"]}
    assert "branch:main" in sources
    assert sources["branch:main"]["status"] in {"passed", "failed", "error"}
    assert "branch:nonexistent" not in sources


def test_query_keyword_filter(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = _make_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "last-red",
        "--database-url",
        db_url,
        "-k",
        "flaky",
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    nodes = {item["nodeid"] for item in payload["items"]}
    assert nodes == {"pkg/test_sample.py::test_flaky"}


def test_query_output_to_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = _make_db(tmp_path)
    out_file = tmp_path / "results.json"
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "last-red",
        "--database-url",
        db_url,
        "--output",
        str(out_file),
        "--format",
        "json",
    ])
    assert exit_code == 0
    assert out_file.exists()
    written = json.loads(out_file.read_text())
    assert written["kind"] == "last-red"


def test_query_with_sync_sqlite_url(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = _make_db(tmp_path).replace("sqlite+aiosqlite", "sqlite")
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "last-red",
        "--database-url",
        db_url,
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["items"], "Expected results when using sync sqlite URL"


def test_query_errors_truncation_and_stream_flags(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_path = tmp_path / "db.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    long_msg = "x" * 600
    _insert_run(
        engine,
        run_id="rx",
        nodeid="pkg/test_long.py::test_long",
        status="failed",
        head_sha="feedfeed",
        branch="main",
        created_at=now,
        message=long_msg,
        detail=long_msg,
        stdout=long_msg,
        stderr=long_msg,
    )
    db_url = f"sqlite+aiosqlite:///{db_path}"

    exit_code = cli_main([
        "query",
        "errors",
        "--database-url",
        db_url,
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    item = payload["items"][0]
    assert len(item["message"]) <= 400
    assert "stdout_text" not in item
    assert "stderr_text" not in item

    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "errors",
        "--database-url",
        db_url,
        "--format",
        "json",
        "--include-stdout",
        "--include-stderr",
        "--max-chars",
        "0",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    item = payload["items"][0]
    assert item["stdout_text"].startswith("x" * 10)
    assert len(item["stdout_text"]) == 600


def test_query_timeline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url, _ = _make_timeline_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "timeline",
        "--database-url",
        db_url,
        "--runs",
        "3",
        "--max-tests",
        "5",
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "timeline"
    assert len(payload["runs"]) == 3
    assert payload["items"][0]["statuses"][0] in {"failed", "passed", "error", "?"}


def test_timeline_marks_missing_tests_as_unknown(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = _make_timeline_with_gap(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "timeline",
        "--database-url",
        db_url,
        "--runs",
        "2",
        "--max-tests",
        "5",
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "timeline"
    assert len(payload["runs"]) == 2
    statuses = payload["items"][0]["statuses"]
    assert statuses == ["?", "failed"]


def test_query_label_and_since(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = _make_label_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "last-green",
        "--database-url",
        db_url,
        "--labels",
        "smoke",
        "--since",
        "5d",
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["items"], "Expected item filtered by label and since"
    assert payload["items"][0]["head_sha"] == "aa"


def test_query_filters_by_positional_selectors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = _make_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "last-red",
        "--database-url",
        db_url,
        "--format",
        "json",
        "pkg/test_sample.py::test_flaky",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    nodes = {item["nodeid"] for item in payload["items"]}
    assert nodes == {"pkg/test_sample.py::test_flaky"}


def test_query_filters_by_pytest_select_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = _make_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "last-red",
        "--database-url",
        db_url,
        "--format",
        "json",
        "--pytest-select=-m slow -k other pkg/test_other.py",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    nodes = {item["nodeid"] for item in payload["items"]}
    assert nodes == {"pkg/test_other.py::test_other"}


def test_explicit_keyword_beats_pytest_select_keyword(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = _make_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "last-red",
        "--database-url",
        db_url,
        "--format",
        "json",
        "-k",
        "flaky",
        "--pytest-select=-k other",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    nodes = {item["nodeid"] for item in payload["items"]}
    assert nodes == {"pkg/test_sample.py::test_flaky"}


def test_selector_normalizes_backslashes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = _make_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "last-red",
        "--database-url",
        db_url,
        "--format",
        "json",
        r"pkg\test_sample.py::test_flaky",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    nodes = {item["nodeid"] for item in payload["items"]}
    assert nodes == {"pkg/test_sample.py::test_flaky"}


def test_selector_substring_match(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db_url = _make_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "last-red",
        "--database-url",
        db_url,
        "--format",
        "json",
        "test_flaky",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    nodes = {item["nodeid"] for item in payload["items"]}
    assert nodes == {"pkg/test_sample.py::test_flaky"}


def _make_duration_db(tmp_path: Path) -> str:
    """Create DB with tests of varying durations for slowest/stats testing."""
    db_path = tmp_path / "duration.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    # test_fast: 0.01s passed
    with Session(engine) as session:
        run = TestRun(
            id="r-fast",
            created_at=now - timedelta(hours=1),
            project="proj",
            suite="suite",
            status="PASS",
            head_sha="sha1",
            code_hash="hash",
            branch="main",
            parent_sha="",
            origin_url="",
            describe="",
            commit_timestamp=now.isoformat(),
            is_dirty=False,
            gpu="cpu",
            marks="smoke",
            pytest_args="",
            platform="linux",
            python_version="3.12",
            host="localhost",
            tests=1,
            failures=0,
            errors=0,
            skipped=0,
            passed=1,
            time_sec=0.01,
            env={},
            junit={},
            ci={},
            report_dir="",
            run_key="r-fast-key",
        )
        session.add(run)
        session.add(
            TestCase(
                run_id="r-fast",
                nodeid="pkg/test_perf.py::test_fast",
                classname="pkg/test_perf.py",
                name="test_fast",
                status="passed",
                time_sec=0.01,
                message="",
                detail="",
                stdout_text="",
                stderr_text="",
            )
        )
        session.commit()

    # test_slow: 2.5s failed
    with Session(engine) as session:
        run = TestRun(
            id="r-slow",
            created_at=now - timedelta(minutes=30),
            project="proj",
            suite="suite",
            status="FAIL",
            head_sha="sha2",
            code_hash="hash",
            branch="main",
            parent_sha="",
            origin_url="",
            describe="",
            commit_timestamp=now.isoformat(),
            is_dirty=False,
            gpu="cpu",
            marks="smoke",
            pytest_args="",
            platform="linux",
            python_version="3.12",
            host="localhost",
            tests=1,
            failures=1,
            errors=0,
            skipped=0,
            passed=0,
            time_sec=2.5,
            env={},
            junit={},
            ci={},
            report_dir="",
            run_key="r-slow-key",
        )
        session.add(run)
        session.add(
            TestCase(
                run_id="r-slow",
                nodeid="pkg/test_perf.py::test_slow",
                classname="pkg/test_perf.py",
                name="test_slow",
                status="failed",
                time_sec=2.5,
                message="timeout",
                detail="took too long",
                stdout_text="",
                stderr_text="",
            )
        )
        session.commit()

    # test_medium: 0.5s passed
    with Session(engine) as session:
        run = TestRun(
            id="r-medium",
            created_at=now - timedelta(minutes=15),
            project="proj",
            suite="suite",
            status="PASS",
            head_sha="sha3",
            code_hash="hash",
            branch="main",
            parent_sha="",
            origin_url="",
            describe="",
            commit_timestamp=now.isoformat(),
            is_dirty=False,
            gpu="cpu",
            marks="smoke",
            pytest_args="",
            platform="linux",
            python_version="3.12",
            host="localhost",
            tests=1,
            failures=0,
            errors=0,
            skipped=0,
            passed=1,
            time_sec=0.5,
            env={},
            junit={},
            ci={},
            report_dir="",
            run_key="r-medium-key",
        )
        session.add(run)
        session.add(
            TestCase(
                run_id="r-medium",
                nodeid="pkg/test_perf.py::test_medium",
                classname="pkg/test_perf.py",
                name="test_medium",
                status="passed",
                time_sec=0.5,
                message="",
                detail="",
                stdout_text="",
                stderr_text="",
            )
        )
        session.commit()

    return f"sqlite+aiosqlite:///{db_path}"


def _make_flaky_db(tmp_path: Path) -> str:
    """Create DB with a flaky test (multiple runs with varying outcomes)."""
    db_path = tmp_path / "flaky.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    # Create 5 runs for test_flaky: 3 passed, 2 failed = 40% failure rate
    statuses = ["passed", "failed", "passed", "failed", "passed"]
    for idx, status in enumerate(statuses):
        run_id = f"rf{idx}"
        with Session(engine) as session:
            run = TestRun(
                id=run_id,
                created_at=now - timedelta(hours=idx),
                project="proj",
                suite="suite",
                status="PASS" if status == "passed" else "FAIL",
                head_sha=f"sha{idx}",
                code_hash="hash",
                branch="main",
                parent_sha="",
                origin_url="",
                describe="",
                commit_timestamp=now.isoformat(),
                is_dirty=False,
                gpu="cpu",
                marks="smoke",
                pytest_args="",
                platform="linux",
                python_version="3.12",
                host="localhost",
                tests=1,
                failures=0 if status == "passed" else 1,
                errors=0,
                skipped=0,
                passed=1 if status == "passed" else 0,
                time_sec=0.1 + idx * 0.05,
                env={},
                junit={},
                ci={},
                report_dir="",
                run_key=f"{run_id}-key",
            )
            session.add(run)
            session.add(
                TestCase(
                    run_id=run_id,
                    nodeid="pkg/test_flaky.py::test_flaky",
                    classname="pkg/test_flaky.py",
                    name="test_flaky",
                    status=status,
                    time_sec=0.1 + idx * 0.05,
                    message="" if status == "passed" else "flaky failure",
                    detail="",
                    stdout_text="",
                    stderr_text="",
                )
            )
            session.commit()

    # Add a stable test with 3 runs, all passed = 0% failure rate
    for idx in range(3):
        run_id = f"rs{idx}"
        with Session(engine) as session:
            run = TestRun(
                id=run_id,
                created_at=now - timedelta(hours=idx + 10),
                project="proj",
                suite="suite",
                status="PASS",
                head_sha=f"stable_sha{idx}",
                code_hash="hash",
                branch="main",
                parent_sha="",
                origin_url="",
                describe="",
                commit_timestamp=now.isoformat(),
                is_dirty=False,
                gpu="cpu",
                marks="smoke",
                pytest_args="",
                platform="linux",
                python_version="3.12",
                host="localhost",
                tests=1,
                failures=0,
                errors=0,
                skipped=0,
                passed=1,
                time_sec=0.05,
                env={},
                junit={},
                ci={},
                report_dir="",
                run_key=f"{run_id}-key",
            )
            session.add(run)
            session.add(
                TestCase(
                    run_id=run_id,
                    nodeid="pkg/test_stable.py::test_stable",
                    classname="pkg/test_stable.py",
                    name="test_stable",
                    status="passed",
                    time_sec=0.05,
                    message="",
                    detail="",
                    stdout_text="",
                    stderr_text="",
                )
            )
            session.commit()

    return f"sqlite+aiosqlite:///{db_path}"


def test_query_slowest_basic(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test that slowest query returns tests ordered by duration."""
    db_url = _make_duration_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "slowest",
        "--database-url",
        db_url,
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "slowest"
    items = payload["items"]
    assert len(items) == 3

    # Should be sorted by time_sec descending (slowest first)
    times = [item["time_sec"] for item in items]
    assert times == sorted(times, reverse=True)
    assert items[0]["nodeid"] == "pkg/test_perf.py::test_slow"
    assert items[0]["time_sec"] == pytest.approx(2.5)


def test_query_slowest_with_status_filter(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test filtering slowest query by status."""
    db_url = _make_duration_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "slowest",
        "--database-url",
        db_url,
        "--status",
        "failed",
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    items = payload["items"]
    # Only the failed test should be returned
    assert len(items) == 1
    assert items[0]["status"] == "failed"
    assert items[0]["nodeid"] == "pkg/test_perf.py::test_slow"


def test_query_slowest_with_limit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test limiting slowest query results."""
    db_url = _make_duration_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "slowest",
        "--database-url",
        db_url,
        "--limit",
        "2",
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    items = payload["items"]
    assert len(items) == 2
    # Should still be sorted by time
    assert items[0]["time_sec"] > items[1]["time_sec"]


def test_query_stats_failure_rate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test that stats query calculates failure rates correctly."""
    db_url = _make_flaky_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "stats",
        "--database-url",
        db_url,
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "stats"
    items = payload["items"]
    assert len(items) == 2

    # Default sort is by failure rate descending
    flaky_test = next(i for i in items if "test_flaky" in i["nodeid"])
    stable_test = next(i for i in items if "test_stable" in i["nodeid"])

    assert flaky_test["total_runs"] == 5
    assert flaky_test["failures"] == 2
    assert flaky_test["passes"] == 3
    assert flaky_test["failure_rate"] == pytest.approx(40.0)

    assert stable_test["total_runs"] == 3
    assert stable_test["failures"] == 0
    assert stable_test["passes"] == 3
    assert stable_test["failure_rate"] == pytest.approx(0.0)

    # Flaky should come first (higher failure rate)
    assert items[0]["nodeid"] == flaky_test["nodeid"]


def test_query_stats_min_runs_filter(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test filtering stats by minimum run count."""
    db_url = _make_flaky_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "stats",
        "--database-url",
        db_url,
        "--min-runs",
        "4",
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    items = payload["items"]
    # Only test_flaky has >= 4 runs
    assert len(items) == 1
    assert items[0]["nodeid"] == "pkg/test_flaky.py::test_flaky"


def test_query_stats_sort_by_avg_time(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test sorting stats by average time."""
    db_url = _make_flaky_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "stats",
        "--database-url",
        db_url,
        "--sort-by",
        "avg-time",
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    items = payload["items"]
    # Should be sorted by avg_time_sec descending
    avg_times = [item["avg_time_sec"] for item in items]
    assert avg_times == sorted(avg_times, reverse=True)


def test_query_stats_with_time_range(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test stats query with time range filter."""
    db_url = _make_flaky_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "stats",
        "--database-url",
        db_url,
        "--since",
        "6h",
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    items = payload["items"]
    # Only test_flaky runs are within last 6 hours (indices 0-4)
    # test_stable runs are 10+ hours ago
    assert len(items) == 1
    assert items[0]["nodeid"] == "pkg/test_flaky.py::test_flaky"


def test_format_time_styled_smart_units() -> None:
    """Test that _format_time_styled uses appropriate units."""
    from pytest_chronicle.cli.query_cmd import _format_time_styled

    # Seconds (>= 1s)
    result = _format_time_styled(2.5)
    assert result.plain == "2.50s"

    # Milliseconds (>= 1ms, < 1s)
    result = _format_time_styled(0.123)
    assert result.plain == "123ms"

    # Microseconds (< 1ms)
    result = _format_time_styled(0.000456)
    assert result.plain == "456μs"

    # Empty for invalid input
    result = _format_time_styled(None)
    assert result.plain == ""


def test_format_time_styled_slow_highlighting() -> None:
    """Test that slow tests get highlighted styling."""
    from pytest_chronicle.cli.query_cmd import _format_time_styled, SLOW_THRESHOLD, VERY_SLOW_THRESHOLD

    # Fast test - no special styling
    fast = _format_time_styled(0.1)
    assert fast.style is None or str(fast.style) == ""

    # Slow test (>= SLOW_THRESHOLD) - yellow styling
    slow = _format_time_styled(SLOW_THRESHOLD + 0.1)
    assert "yellow" in str(slow.style)

    # Very slow test (>= VERY_SLOW_THRESHOLD) - red styling
    very_slow = _format_time_styled(VERY_SLOW_THRESHOLD + 1)
    assert "red" in str(very_slow.style)


def test_query_timeline_includes_times(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test timeline query includes times in the data."""
    db_url, _ = _make_timeline_db(tmp_path)
    capsys.readouterr()
    exit_code = cli_main([
        "query",
        "timeline",
        "--database-url",
        db_url,
        "--runs",
        "3",
        "--format",
        "json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["kind"] == "timeline"
    # Verify times are included in the data
    items = payload["items"]
    assert len(items) > 0
    assert "times" in items[0]
    # Times should be a list matching the runs length
    assert isinstance(items[0]["times"], list)
