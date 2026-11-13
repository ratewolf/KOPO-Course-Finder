"""독립 질문 → 로컬 SQL 생성 → 검증 → 조회 연결 및 CLI."""

import argparse
import json
import re
import sqlite3
from dataclasses import asdict, dataclass

from .config import Settings
from .data import database_summary
from .model import LocalSQLModel, ModelError
from .query import (
    QueryError,
    QueryResult,
    SQLValidationError,
    execute_query,
    validate_sql,
)
from .summary import result_message


class InputError(ValueError):
    pass


@dataclass(frozen=True)
class Answer:
    question: str
    result: QueryResult
    message: str
    generations: list


class QueryService:
    def __init__(self, settings, model=None):
        self.settings = settings
        self.model = model if model is not None else LocalSQLModel(settings)

    def ask(self, question, *, resolved=False):
        question = question.strip()
        if not question:
            raise InputError("질문을 입력해 주세요.")
        if len(question) > 2000:
            raise InputError("질문이 너무 깁니다. 2,000자 이내로 입력해 주세요.")
        # CLI 직접 호출에서는 생략 표현을 임의 해석하지 않는다.
        if not resolved and re.search(
            r"그중|그럼|이전 결과|앞서|방금|그것|그 강좌|그 과목|은\s*\?|는\s*\?"
            r"|^(?:NCS|[12]학기|[12]학년)만",
            question,
        ):
            raise InputError(
                "후속 질문은 아직 지원하지 않습니다. 조회 조건을 모두 포함해 입력해 주세요."
            )
        if re.search(r"학점|수강\s*인원|강의\s*시간|강의실|교양|시간표", question):
            raise InputError("학점·수강 인원·시간·강의실·교양 구분은 자료에 없습니다.")
        if re.search(r"올해|작년|내년|이번\s*학기|지난\s*학기", question):
            raise InputError("학년도와 학기를 숫자로 명시해 주세요.")
        connection = None
        try:
            connection = sqlite3.connect(
                self.settings.database.resolve().as_uri() + "?mode=ro", uri=True
            )
            metadata = database_summary(connection)
        except sqlite3.Error:
            raise QueryError(
                "조회 DB를 읽을 수 없습니다. 먼저 엑셀을 적재해 주세요."
            ) from None
        finally:
            if connection is not None:
                connection.close()
        years = {r["year"] for r in metadata["coverage"]}
        requested = {
            int(y) for y in re.findall(r"(?<!\d)(\d{4})\s*(?:학년도|년도|년)", question)
        }
        if not years:
            raise InputError("적재된 강좌가 없습니다.")
        if requested - years:
            raise InputError(
                f"조회 가능한 학년도: {', '.join(map(str, sorted(years)))}"
            )
        correction = None
        generations = []
        for attempt in range(2):
            generation = self.model.generate(
                question, metadata["coverage"], metadata["departments"], correction
            )
            generations.append(generation)
            try:
                sql, _ = validate_sql(generation.sql)
            except SQLValidationError as exc:
                if attempt == 0:
                    correction = str(exc)
                    continue
                raise SQLValidationError(
                    "SQL 검증에 두 번 실패했습니다. 조건을 구체적으로 입력해 주세요."
                ) from None
            result = execute_query(
                self.settings.database,
                sql,
                self.settings.max_rows,
                self.settings.sql_seconds,
            )
            return Answer(question, result, result_message(result), generations)


def main():
    parser = argparse.ArgumentParser(description="독립적인 한국어 질문으로 강좌 조회")
    parser.add_argument(
        "question", nargs="+", help="여러 질문을 인자로 주면 모델을 재사용합니다."
    )
    args = parser.parse_args()
    try:
        settings = Settings.from_env()
    except ValueError as exc:
        parser.exit(1, f"설정 오류: {exc}\n")
    service = QueryService(settings)
    failed = False
    for question in args.question:
        try:
            answer = service.ask(question)
            payload = asdict(answer)
            payload["model_load_seconds"] = service.model.load_seconds
            print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
        except (InputError, ModelError, SQLValidationError, QueryError) as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False), flush=True)
            failed = True
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
