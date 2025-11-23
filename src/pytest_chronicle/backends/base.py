from __future__ import annotations

from typing import Protocol, Any


class QueryBackend(Protocol):
    def last_red(self, params: "QueryParams") -> list[dict[str, Any]]: ...
    def errors(self, params: "QueryParams") -> list[dict[str, Any]]: ...
    def flipped_green(self, params: "QueryParams") -> list[dict[str, Any]]: ...
    def compare(self, params: "QueryParams", branches: list[str], commits: list[str]) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...


class QueryParams:
    def __init__(
        self,
        *,
        project_like: str,
        suite: str | None,
        branches: list[str],
        commits: list[str],
        keyword: str | None,
        marks: str | None,
        limit: int,
    ) -> None:
        self.project_like = project_like
        self.suite = suite
        self.branches = branches
        self.commits = commits
        self.keyword = keyword
        self.marks = marks
        self.limit = limit

    def with_limit(self, new_limit: int) -> "QueryParams":
        return QueryParams(
            project_like=self.project_like,
            suite=self.suite,
            branches=self.branches,
            commits=self.commits,
            keyword=self.keyword,
            marks=self.marks,
            limit=new_limit,
        )

