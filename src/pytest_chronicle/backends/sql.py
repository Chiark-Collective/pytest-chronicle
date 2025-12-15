from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import create_engine, text  # type: ignore

from pytest_chronicle.backends.base import QueryBackend, QueryParams


def _sync_url(db_url: str) -> str:
    if db_url.startswith("sqlite+aiosqlite://"):
        return db_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    if db_url.startswith("postgresql+asyncpg://"):
        return db_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    return db_url


class _ExprNode:
    def eval(self, haystacks: Iterable[str]) -> bool:  # pragma: no cover
        raise NotImplementedError


class _Term(_ExprNode):
    def __init__(self, term: str) -> None:
        if (term.startswith("\"") and term.endswith("\"")) or (term.startswith("'") and term.endswith("'")):
            term = term[1:-1]
        self.term = term

    def eval(self, haystacks: Iterable[str]) -> bool:
        return any(self.term in h for h in haystacks if h)


class _Not(_ExprNode):
    def __init__(self, node: _ExprNode) -> None:
        self.node = node

    def eval(self, haystacks: Iterable[str]) -> bool:
        return not self.node.eval(haystacks)


class _And(_ExprNode):
    def __init__(self, left: _ExprNode, right: _ExprNode) -> None:
        self.left = left
        self.right = right

    def eval(self, haystacks: Iterable[str]) -> bool:
        return self.left.eval(haystacks) and self.right.eval(haystacks)


class _Or(_ExprNode):
    def __init__(self, left: _ExprNode, right: _ExprNode) -> None:
        self.left = left
        self.right = right

    def eval(self, haystacks: Iterable[str]) -> bool:
        return self.left.eval(haystacks) or self.right.eval(haystacks)


def _tokenize(expr: str) -> list[str]:
    pattern = r"\(|\)|\band\b|\bor\b|\bnot\b|[^()\s]+"
    return [tok for tok in re.findall(pattern, expr, flags=re.IGNORECASE) if tok.strip()]


def _parse_expr(tokens: list[str]) -> _ExprNode:
    pos = 0

    def peek() -> str | None:
        return tokens[pos] if pos < len(tokens) else None

    def consume() -> str:
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        return tok

    def parse_factor() -> _ExprNode:
        tok = peek()
        if tok is None:
            return _Term("")
        if tok.lower() == "not":
            consume()
            return _Not(parse_factor())
        if tok == "(":
            consume()
            node = parse_or()
            if peek() == ")":
                consume()
            return node
        return _Term(consume())

    def parse_and() -> _ExprNode:
        node = parse_factor()
        while True:
            tok = peek()
            if tok is None or tok.lower() != "and":
                break
            consume()
            node = _And(node, parse_factor())
        return node

    def parse_or() -> _ExprNode:
        node = parse_and()
        while True:
            tok = peek()
            if tok is None or tok.lower() != "or":
                break
            consume()
            node = _Or(node, parse_and())
        return node

    return parse_or()


def _matches_keyword(expr: str | None, haystacks: Iterable[str]) -> bool:
    if not expr:
        return True
    tokens = _tokenize(expr)
    if not tokens:
        return True
    tree = _parse_expr(tokens)
    return tree.eval(haystacks)


def _normalize_selector(selector: str) -> str:
    selector = selector.strip()
    selector = selector.replace("\\", "/")
    if selector.startswith("./"):
        selector = selector[2:]
    return selector


def _matches_selector_list(selectors: list[str], nodeid: str) -> bool:
    if not selectors:
        return True
    normalized_nodeid = str(nodeid or "").replace("\\", "/")
    for sel in selectors:
        if not sel:
            continue
        # pytest nodeid selection is prefix-based; allow substring fallback.
        if normalized_nodeid.startswith(sel):
            return True
        if sel in normalized_nodeid:
            return True
    return False


def _in_clause(column: str, prefix: str, values: list[str]) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {}
    if not values:
        return "1 = 1", params
    placeholders: list[str] = []
    for idx, value in enumerate(values):
        key = f"{prefix}_{idx}"
        placeholders.append(f":{key}")
        params[key] = value
    return f"{column} IN ({', '.join(placeholders)})", params


def _build_where(common: QueryParams, *, include_status: bool = False) -> tuple[str, dict[str, Any]]:
    clauses = ["tr.project LIKE :project_like"]
    params: dict[str, Any] = {"project_like": common.project_like}
    if common.suite:
        clauses.append("tr.suite = :suite")
        params["suite"] = common.suite
    if common.labels:
        clauses.append("tr.suite = :labels")
        params["labels"] = common.labels
    if common.branches:
        clause, extras = _in_clause("tr.branch", "branch", common.branches)
        clauses.append(clause)
        params.update(extras)
    if common.commits:
        clause, extras = _in_clause("tr.head_sha", "commit", common.commits)
        clauses.append(clause)
        params.update(extras)
    if common.since:
        clauses.append("tr.created_at >= :since_ts")
        params["since_ts"] = common.since
    if common.until:
        clauses.append("tr.created_at <= :until_ts")
        params["until_ts"] = common.until
    if include_status and common.statuses:
        clause, extras = _in_clause("tc.status", "status", common.statuses)
        clauses.append(clause)
        params.update(extras)
    return " AND ".join(clauses), params


def _filter_and_trim(rows: list[dict[str, Any]], common: QueryParams, apply_limit: bool = True) -> list[dict[str, Any]]:
    selectors = [_normalize_selector(sel) for sel in common.selectors if sel]
    filtered: list[dict[str, Any]] = []
    for row in rows:
        nodeid = row.get("nodeid", "")
        if selectors and not _matches_selector_list(selectors, nodeid):
            continue
        if not _matches_keyword(common.keyword, [nodeid, row.get("classname", ""), row.get("name", "")]):
            continue
        if common.marks and not _matches_keyword(common.marks, [row.get("marks", "")]):
            continue
        filtered.append(dict(row))

    def _sort_key(row: dict[str, Any]) -> tuple[datetime, str]:
        ts = row.get("created_at")
        if isinstance(ts, datetime):
            dt = ts
        else:
            try:
                dt = datetime.fromisoformat(str(ts))
            except Exception:
                dt = datetime.min
        return (dt, row.get("nodeid", ""))

    filtered.sort(key=_sort_key, reverse=True)
    if apply_limit and common.limit:
        filtered = filtered[: common.limit]
    return filtered


class SqlQueryBackend(QueryBackend):
    def __init__(self, db_url: str) -> None:
        self._engine = create_engine(_sync_url(db_url))

    def close(self) -> None:
        self._engine.dispose()

    def last_red(self, common: QueryParams) -> list[dict[str, Any]]:
        where_sql, params = _build_where(common)
        sql = f"""
        WITH filtered AS (
            SELECT
                tc.nodeid,
                tc.classname,
                tc.name,
                tc.status,
                tc.message,
                tc.detail,
                tc.time_sec,
                tr.head_sha,
                tr.branch,
                tr.created_at,
                tr.id AS run_id,
                tr.marks
            FROM test_cases tc
            JOIN test_runs tr ON tr.id = tc.run_id
            WHERE {where_sql}
              AND tc.status IN ('failed','error')
        ),
        ranked AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY nodeid ORDER BY created_at DESC) AS rn
            FROM filtered
        )
        SELECT * FROM ranked WHERE rn = 1 ORDER BY created_at DESC;
        """
        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return _filter_and_trim(rows, common)

    def last_green(self, common: QueryParams) -> list[dict[str, Any]]:
        where_sql, params = _build_where(common)
        sql = f"""
        WITH filtered AS (
            SELECT
                tc.nodeid,
                tc.classname,
                tc.name,
                tc.status,
                tc.message,
                tc.detail,
                tc.time_sec,
                tr.head_sha,
                tr.branch,
                tr.created_at,
                tr.id AS run_id,
                tr.marks
            FROM test_cases tc
            JOIN test_runs tr ON tr.id = tc.run_id
            WHERE {where_sql}
              AND tc.status = 'passed'
        ),
        ranked AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY nodeid ORDER BY created_at DESC) AS rn
            FROM filtered
        )
        SELECT * FROM ranked WHERE rn = 1 ORDER BY created_at DESC;
        """
        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return _filter_and_trim(rows, common)

    def errors(self, common: QueryParams) -> list[dict[str, Any]]:
        where_sql, params = _build_where(common)
        sql = f"""
        WITH filtered AS (
            SELECT
                tc.nodeid,
                tc.classname,
                tc.name,
                tc.status,
                tc.message,
                tc.detail,
                tc.stdout_text,
                tc.stderr_text,
                tc.time_sec,
                tr.head_sha,
                tr.branch,
                tr.created_at,
                tr.id AS run_id,
                tr.marks
            FROM test_cases tc
            JOIN test_runs tr ON tr.id = tc.run_id
            WHERE {where_sql}
              AND tc.status IN ('failed','error')
        ),
        ranked AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY nodeid ORDER BY created_at DESC) AS rn
            FROM filtered
        )
        SELECT * FROM ranked WHERE rn = 1 ORDER BY created_at DESC;
        """
        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return _filter_and_trim(rows, common)

    def flipped_green(self, common: QueryParams) -> list[dict[str, Any]]:
        where_sql, params = _build_where(common)
        sql = f"""
        WITH ordered AS (
            SELECT
                tc.nodeid,
                tc.classname,
                tc.name,
                tc.status,
                tc.time_sec,
                tr.head_sha,
                tr.branch,
                tr.created_at,
                tr.id AS run_id,
                tr.marks,
                LAG(tc.status) OVER (PARTITION BY tc.nodeid ORDER BY tr.created_at) AS prev_status,
                LAG(tr.head_sha) OVER (PARTITION BY tc.nodeid ORDER BY tr.created_at) AS prev_head_sha,
                LAG(tr.created_at) OVER (PARTITION BY tc.nodeid ORDER BY tr.created_at) AS prev_created_at
            FROM test_cases tc
            JOIN test_runs tr ON tr.id = tc.run_id
            WHERE {where_sql}
        ),
        flips AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY nodeid ORDER BY created_at DESC) AS rn
            FROM ordered
            WHERE status IN ('passed', 'xpassed') AND prev_status IN ('failed', 'error', 'xfailed')
        )
        SELECT * FROM flips WHERE rn = 1 ORDER BY created_at DESC;
        """
        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        return _filter_and_trim(rows, common)

    def _fetch_latest_for_source(self, common: QueryParams, label: str, extra_clause: str, extra_params: dict[str, Any]) -> dict[str, dict[str, Any]]:
        where_sql, params = _build_where(common)
        where_sql = f"{where_sql} AND {extra_clause}" if extra_clause else where_sql
        params = {**params, **extra_params}
        sql = f"""
        WITH ranked AS (
            SELECT
                tc.nodeid,
                tc.classname,
                tc.name,
                tc.status,
                tc.time_sec,
                tr.head_sha,
                tr.branch,
                tr.created_at,
                tr.id AS run_id,
                tr.marks,
                ROW_NUMBER() OVER (PARTITION BY tc.nodeid ORDER BY tr.created_at DESC) AS rn
            FROM test_cases tc
            JOIN test_runs tr ON tr.id = tc.run_id
            WHERE {where_sql}
        )
        SELECT * FROM ranked WHERE rn = 1;
        """
        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()
        filtered = _filter_and_trim(rows, common, apply_limit=False)
        result: dict[str, dict[str, Any]] = {}
        for row in filtered:
            row = dict(row)
            row["source"] = label
            result[row["nodeid"]] = row
        return result

    def compare(self, common: QueryParams, branches: list[str], commits: list[str]) -> list[dict[str, Any]]:
        sources: list[tuple[str, str, dict[str, Any]]] = []
        for idx, branch in enumerate(branches):
            clause, params = _in_clause("tr.branch", f"cmp_branch_{idx}", [branch])
            sources.append((f"branch:{branch}", clause, params))
        for idx, commit in enumerate(commits):
            clause, params = _in_clause("tr.head_sha", f"cmp_commit_{idx}", [commit])
            sources.append((f"commit:{commit}", clause, params))

        results: dict[str, dict[str, Any]] = {}
        for label, clause, extra_params in sources:
            per_source = self._fetch_latest_for_source(common, label, clause, extra_params)
            for nodeid, row in per_source.items():
                bucket = results.setdefault(nodeid, {"nodeid": nodeid, "sources": []})
                bucket["sources"].append(row)

        filtered: list[dict[str, Any]] = []
        for nodeid, entry in results.items():
            if not entry.get("sources"):
                continue
            sample = entry["sources"][0]
            if not _matches_keyword(common.keyword, [nodeid, sample.get("classname", ""), sample.get("name", "")]):
                continue
            if common.marks and not _matches_keyword(common.marks, [sample.get("marks", "")]):
                continue
            filtered.append(entry)

        filtered.sort(key=lambda item: item["nodeid"])
        if common.limit:
            filtered = filtered[: common.limit]
        return filtered

    def timeline(self, common: QueryParams, runs: int, max_tests: int | None) -> dict[str, Any]:
        """Return a matrix of recent runs vs test statuses."""
        where_sql, params = _build_where(common)
        params = dict(params)
        params["run_limit"] = runs
        sql_runs = f"""
        SELECT tr.id, tr.head_sha, tr.branch, tr.created_at, tr.marks
        FROM test_runs tr
        WHERE {where_sql}
        ORDER BY tr.created_at DESC
        LIMIT :run_limit;
        """
        with self._engine.connect() as conn:
            run_rows = conn.execute(text(sql_runs), params).mappings().all()
        if not run_rows:
            return {"kind": "timeline", "runs": [], "items": []}

        run_ids = [row["id"] for row in run_rows]
        placeholder_ids = ", ".join([f":r{idx}" for idx, _ in enumerate(run_ids)])
        params_cases: dict[str, Any] = {f"r{idx}": run_id for idx, run_id in enumerate(run_ids)}
        sql_cases = f"""
        SELECT tc.run_id, tc.nodeid, tc.classname, tc.name, tc.status, tc.time_sec
        FROM test_cases tc
        WHERE tc.run_id IN ({placeholder_ids});
        """
        with self._engine.connect() as conn:
            case_rows = conn.execute(text(sql_cases), params_cases).mappings().all()

        # Build run metadata with optional marks filtering.
        runs_meta: list[dict[str, Any]] = []
        marks_ok: list[bool] = []
        for row in run_rows:
            ok = True
            if common.marks and not _matches_keyword(common.marks, [row.get("marks", "")]):
                ok = False
            marks_ok.append(ok)
            runs_meta.append(
                {
                    "id": row["id"],
                    "head_sha": row.get("head_sha"),
                    "branch": row.get("branch"),
                    "created_at": row.get("created_at"),
                }
            )

        matrix: dict[str, dict[str, Any]] = {}
        for case in case_rows:
            run_id = case["run_id"]
            try:
                col_idx = run_ids.index(run_id)
            except ValueError:
                continue
            if not marks_ok[col_idx]:
                continue  # skip this run due to marks filter
            nodeid = case["nodeid"]
            row_entry = matrix.setdefault(
                nodeid,
                {
                    "nodeid": nodeid,
                    "classname": case.get("classname", ""),
                    "name": case.get("name", ""),
                    "statuses": ["?" for _ in run_ids],
                    "times": [None for _ in run_ids],
                },
            )
            row_entry["statuses"][col_idx] = case.get("status", "?")
            row_entry["times"][col_idx] = case.get("time_sec")

        # Filter by keyword after aggregation.
        filtered_items: list[dict[str, Any]] = []
        for entry in matrix.values():
            if not _matches_keyword(common.keyword, [entry.get("nodeid", ""), entry.get("classname", ""), entry.get("name", "")]):
                continue
            filtered_items.append(entry)

        filtered_items.sort(key=lambda e: e["nodeid"])
        if max_tests is not None:
            filtered_items = filtered_items[: max_tests]

        return {"kind": "timeline", "runs": runs_meta, "items": filtered_items}

    def slowest(self, common: QueryParams) -> list[dict[str, Any]]:
        """Return tests ordered by execution time (slowest first), one per nodeid."""
        where_sql, params = _build_where(common, include_status=True)
        sql = f"""
        WITH filtered AS (
            SELECT
                tc.nodeid,
                tc.classname,
                tc.name,
                tc.status,
                tc.time_sec,
                tc.message,
                tc.detail,
                tr.head_sha,
                tr.branch,
                tr.created_at,
                tr.id AS run_id,
                tr.marks
            FROM test_cases tc
            JOIN test_runs tr ON tr.id = tc.run_id
            WHERE {where_sql}
        ),
        ranked AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY nodeid ORDER BY created_at DESC) AS rn
            FROM filtered
        )
        SELECT * FROM ranked WHERE rn = 1 ORDER BY time_sec DESC;
        """
        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()

        # Apply filtering but preserve time-based ordering
        selectors = [_normalize_selector(sel) for sel in common.selectors if sel]
        filtered: list[dict[str, Any]] = []
        for row in rows:
            nodeid = row.get("nodeid", "")
            if selectors and not _matches_selector_list(selectors, nodeid):
                continue
            if not _matches_keyword(common.keyword, [nodeid, row.get("classname", ""), row.get("name", "")]):
                continue
            if common.marks and not _matches_keyword(common.marks, [row.get("marks", "")]):
                continue
            filtered.append(dict(row))

        # Do NOT re-sort - preserve time_sec DESC ordering from SQL
        if common.limit:
            filtered = filtered[: common.limit]
        return filtered

    def stats(self, common: QueryParams, sort_by: str = "failure-rate") -> list[dict[str, Any]]:
        """Return aggregated statistics per test including failure rates and timing."""
        where_sql, params = _build_where(common, include_status=True)

        # Determine sort order based on sort_by parameter
        sort_map = {
            "failure-rate": "failure_rate DESC, total_runs DESC",
            "total-runs": "total_runs DESC, failure_rate DESC",
            "avg-time": "avg_time_sec DESC, total_runs DESC",
            "max-time": "max_time_sec DESC, total_runs DESC",
        }
        order_by = sort_map.get(sort_by, "failure_rate DESC, total_runs DESC")

        sql = f"""
        WITH filtered AS (
            SELECT
                tc.nodeid,
                tc.classname,
                tc.name,
                tc.status,
                tc.time_sec,
                tr.head_sha,
                tr.branch,
                tr.created_at,
                tr.id AS run_id,
                tr.marks
            FROM test_cases tc
            JOIN test_runs tr ON tr.id = tc.run_id
            WHERE {where_sql}
        )
        SELECT
            nodeid,
            classname,
            name,
            COUNT(*) AS total_runs,
            SUM(CASE WHEN status IN ('failed', 'error') THEN 1 ELSE 0 END) AS failures,
            SUM(CASE WHEN status = 'passed' THEN 1 ELSE 0 END) AS passes,
            SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) AS skips,
            SUM(CASE WHEN status = 'xfailed' THEN 1 ELSE 0 END) AS xfails,
            SUM(CASE WHEN status = 'xpassed' THEN 1 ELSE 0 END) AS xpasses,
            ROUND(100.0 * SUM(CASE WHEN status IN ('failed','error') THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2) AS failure_rate,
            AVG(time_sec) AS avg_time_sec,
            MAX(time_sec) AS max_time_sec,
            MIN(time_sec) AS min_time_sec
        FROM filtered
        GROUP BY nodeid, classname, name
        ORDER BY {order_by};
        """
        with self._engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()

        # Apply selector and keyword filtering
        selectors = [_normalize_selector(sel) for sel in common.selectors if sel]
        filtered: list[dict[str, Any]] = []
        for row in rows:
            nodeid = row.get("nodeid", "")
            if selectors and not _matches_selector_list(selectors, nodeid):
                continue
            if not _matches_keyword(common.keyword, [nodeid, row.get("classname", ""), row.get("name", "")]):
                continue
            filtered.append(dict(row))

        if common.limit:
            filtered = filtered[: common.limit]
        return filtered
