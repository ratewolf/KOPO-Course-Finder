"""SQL AST 검증과 권한 제한을 적용한 읽기 전용 SQLite 실행."""

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import traverse_scope

from .schema import COLUMNS

FUNCTIONS = {
    "count",
    "sum",
    "avg",
    "min",
    "max",
    "round",
    "abs",
    "coalesce",
    "nullif",
    "lower",
    "upper",
    "length",
    "substr",
    "substring",
    "trim",
    "ltrim",
    "rtrim",
    "like",
    "cast",
}
SCHEMA = {
    "courses": {
        name: "INT" if name in {"year", "semester", "grade"} else "TEXT"
        for name in COLUMNS
    }
}


class SQLValidationError(ValueError):
    """모델에 전달할 고정 오류. 원본 SQL이나 예외는 포함하지 않는다."""


class QueryError(RuntimeError):
    pass


@dataclass(frozen=True)
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[tuple]
    truncated: bool
    aggregate: bool
    seconds: float


def validate_sql(sql):
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 16000:
        raise SQLValidationError("SQL이 비어 있거나 너무 깁니다.")
    try:
        statements = sqlglot.parse(sql, read="sqlite")
        if len(statements) != 1 or not isinstance(statements[0], exp.Select):
            raise SQLValidationError("단일 SELECT만 생성해 주세요.")
        tree = statements[0]
        if len(list(tree.walk())) > 1500:
            raise SQLValidationError("SQL이 너무 복잡합니다.")
        # 모든 계층을 검사해 WITH와 서브쿼리 안의 쓰기도 차단한다.
        forbidden = (
            exp.DDL,
            exp.DML,
            exp.Command,
            exp.Into,
            exp.Lock,
            exp.Union,
            exp.Intersect,
            exp.Except,
            exp.Parameter,
            exp.Placeholder,
        )
        if any(isinstance(node, forbidden) for node in tree.walk()):
            raise SQLValidationError("읽기 전용 SELECT만 생성해 주세요.")
        if any(node.args.get("recursive") for node in tree.find_all(exp.With)):
            raise SQLValidationError("재귀 CTE는 사용할 수 없습니다.")
        for node in tree.find_all(exp.Func):
            name = (
                node.name.lower()
                if isinstance(node, exp.Anonymous)
                else node.sql_name().lower()
            )
            if name not in FUNCTIONS and not isinstance(
                node, (exp.Case, exp.If, exp.And, exp.Or)
            ):
                raise SQLValidationError("허용되지 않은 함수입니다.")
        for table in tree.find_all(exp.Table):
            if table.db or table.catalog or not isinstance(table.this, exp.Identifier):
                raise SQLValidationError("courses 테이블만 사용해 주세요.")
        physical_tables = 0
        for scope in traverse_scope(tree):
            for source in scope.sources.values():
                if isinstance(source, exp.Table):
                    if source.name.lower() != "courses":
                        raise SQLValidationError("courses 테이블만 사용해 주세요.")
                    physical_tables += 1
        if not physical_tables:
            raise SQLValidationError("courses 데이터를 참조해 주세요.")
        qualify(tree.copy(), dialect="sqlite", schema=SCHEMA, infer_schema=False)
        aggregate = bool(tree.args.get("group")) or any(
            node.find_ancestor(exp.Select) is tree
            for node in tree.find_all(exp.AggFunc)
        )
        return tree.sql(dialect="sqlite"), aggregate
    except SQLValidationError:
        raise
    except Exception:
        raise SQLValidationError("SQL 구문 또는 열 이름이 잘못되었습니다.") from None


def _authorize(action, arg1, arg2, database, trigger):
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        if (
            database in {"main", None}
            and arg1 == "courses"
            and (arg2 in COLUMNS or arg2 == "")
        ):
            return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in FUNCTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def execute_query(database, sql, max_rows=200, timeout_seconds=5):
    if not 1 <= max_rows <= 200 or not 0 < timeout_seconds <= 30:
        raise ValueError("조회 제한 설정이 잘못되었습니다.")
    normalized, aggregate = validate_sql(sql)
    start = time.monotonic()
    connection = None
    try:
        connection = sqlite3.connect(
            Path(database).resolve().as_uri() + "?mode=ro",
            timeout=timeout_seconds,
            uri=True,
        )
        connection.execute("PRAGMA query_only=ON")
        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
        connection.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 16000)
        connection.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100)
        connection.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 1)
        connection.set_authorizer(_authorize)
        steps = 0

        def stop():
            nonlocal steps
            steps += 1000
            return steps >= 5_000_000 or time.monotonic() - start >= timeout_seconds

        connection.set_progress_handler(stop, 1000)
        cursor = connection.execute(normalized)
        rows = cursor.fetchmany(max_rows + 1)
        if time.monotonic() - start >= timeout_seconds:
            raise QueryError("조회 시간이 너무 오래 걸려 중단했습니다.")
        return QueryResult(
            normalized,
            [c[0] for c in cursor.description],
            rows[:max_rows],
            len(rows) > max_rows,
            aggregate,
            time.monotonic() - start,
        )
    except sqlite3.Error as exc:
        if getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_INTERRUPT:
            raise QueryError("조회 시간 또는 계산량 제한을 초과했습니다.") from None
        raise QueryError(
            "DB 조회에 실패했습니다. DB 상태와 조회 조건을 확인해 주세요."
        ) from None
    finally:
        if connection is not None:
            connection.close()
