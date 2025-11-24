from __future__ import annotations

from typing import Protocol, Any


class QueryBackend(Protocol):
    def last_red(self, params: "QueryParams") -> list[dict[str, Any]]: ...
    def last_green(self, params: "QueryParams") -> list[dict[str, Any]]: ...
    def errors(self, params: "QueryParams") -> list[dict[str, Any]]: ...
    def flipped_green(self, params: "QueryParams") -> list[dict[str, Any]]: ...
    def compare(self, params: "QueryParams", branches: list[str], commits: list[str]) -> list[dict[str, Any]]: ...
    def timeline(self, params: "QueryParams", runs: int, max_tests: int | None) -> dict[str, Any]: ...
    def close(self) -> None: ...


class QueryParams:
    def __init__(
        self,
        *,
        project_like: str,
        suite: str | None,
        labels: str | None,
        branches: list[str],
        commits: list[str],
        keyword: str | None,
        marks: str | None,
        limit: int,
        since: "datetime | None" = None,
        until: "datetime | None" = None,
    ) -> None:
        self.project_like = project_like
        self.suite = suite
        self.labels = labels
        self.branches = branches
        self.commits = commits
        self.keyword = keyword
        self.marks = marks
        self.limit = limit
        self.since = since
        self.until = until

    def with_limit(self, new_limit: int) -> "QueryParams":
        return QueryParams(
            project_like=self.project_like,
            suite=self.suite,
            labels=self.labels,
            branches=self.branches,
            commits=self.commits,
            keyword=self.keyword,
            marks=self.marks,
            limit=new_limit,
            since=self.since,
            until=self.until,
        )
