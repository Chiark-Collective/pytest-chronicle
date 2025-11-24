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
            suite="suite",
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
        )
    return f"sqlite+aiosqlite:///{db_path}", run_ids


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
    assert payload["items"][0]["statuses"][0] in {"failed", "passed", "error", "."}
