"""운영자용 엑셀 적재 CLI. 원본 값은 오류 메시지에 포함하지 않는다."""

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import warnings
from pathlib import Path

from openpyxl import load_workbook

from .schema import COLUMNS, CREATE_COURSES

HEADERS = (
    "순번",
    "NCS여부",
    "강좌번호",
    "학과",
    "전공",
    "학년",
    "주야",
    "과목코드",
    "과목명",
    "수강반",
    "교직원번호",
    "교수명",
)
FILENAME = re.compile(r"KOPO_정수캠_(\d{4})_([12])학년_([12])학기_개설강좌조회\.xlsx")
TOTAL = re.compile(r"총건수\s*:\s*\[([\d,]+)\]")


class ImportValidationError(ValueError):
    """개인정보를 포함하지 않는 적재 오류."""


def _text(cell):
    if cell.data_type in {"f", "e"}:
        raise ImportValidationError("수식·오류 셀은 허용하지 않습니다.")
    value = cell.value
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if int(value) == value:
            if re.fullmatch(r"0+", cell.number_format):
                return str(int(value)).zfill(len(cell.number_format))
            return str(int(value))
    raise ImportValidationError("문자열 또는 정수 셀만 허용합니다.")


def read_courses(path, key):
    """파일 전체 검증 후 가명 처리된 행과 교체 대상 기간을 반환한다."""
    match = FILENAME.fullmatch(path.name)
    if not match:
        raise ImportValidationError("파일명이 개설강좌 조회 양식과 다릅니다.")
    year, grade, semester = map(int, match.groups())
    if not 1900 <= year <= 2199:
        raise ImportValidationError("학년도 범위가 잘못되었습니다.")
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Workbook contains no default style.*",
            category=UserWarning,
        )
        workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        if len(workbook.worksheets) != 1:
            raise ImportValidationError("시트는 하나여야 합니다.")
        rows = iter(workbook.active.iter_rows())
        header = next(rows, ())
        if tuple(_text(c) for c in header) != HEADERS:
            raise ImportValidationError("열 구성이 개설강좌 조회 양식과 다릅니다.")
        courses, seen = [], set()
        total = None
        for number, cells in enumerate(rows, 2):
            try:
                values = [_text(c) for c in cells]
                if not any(values):
                    continue
                summary = TOTAL.fullmatch(values[0])
                if summary:
                    if total is not None or any(values[1:]):
                        raise ImportValidationError(
                            "총건수 행이 중복되거나 잘못되었습니다."
                        )
                    total = int(summary[1].replace(",", ""))
                    continue
                if total is not None:
                    raise ImportValidationError("총건수 뒤에 데이터가 있습니다.")
                if len(values) != len(HEADERS) or not all(values):
                    raise ImportValidationError("필수 값이 누락되었습니다.")
                if values[0] != str(len(courses) + 1):
                    raise ImportValidationError("순번이 연속되지 않습니다.")
                if values[5] != str(grade):
                    raise ImportValidationError("파일명과 학년 열이 다릅니다.")
                if values[1] not in {"Y", "N"} or values[6] not in {"주간", "야간"}:
                    raise ImportValidationError("NCS 또는 주야 구분이 잘못되었습니다.")
                if values[2] in seen:
                    raise ImportValidationError("강좌번호가 중복되었습니다.")
                seen.add(values[2])
                alias = (
                    "교수_"
                    + hmac.new(
                        key, values[10].encode("utf-8"), hashlib.sha256
                    ).hexdigest()[:16]
                )
                courses.append(
                    (
                        year,
                        semester,
                        grade,
                        values[1],
                        values[2],
                        values[3],
                        values[4],
                        values[6],
                        values[7],
                        values[8],
                        values[9],
                        alias,
                    )
                )
            except ImportValidationError as exc:
                raise ImportValidationError(f"{number}행: {exc}") from None
        if total is None or total != len(courses):
            raise ImportValidationError("총건수 요약과 실제 데이터 행 수가 다릅니다.")
        return (year, semester, grade), courses
    finally:
        workbook.close()


def _load_key(path, existing_database):
    # 원본과 함께 Git 제외된 data/에 보관. 키를 잃으면 기존 가명을 재현할 수 없다.
    if not path.exists():
        if existing_database:
            raise ImportValidationError(
                "기존 DB의 가명 키가 없습니다. 키를 복원해 주세요."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as handle:
                handle.write(secrets.token_bytes(32))
    key = path.read_bytes()
    if len(key) != 32:
        raise ImportValidationError("가명 키 형식이 잘못되었습니다.")
    return key


def database_summary(connection):
    return {
        "rows": connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
        "coverage": [
            {"year": y, "semester": s, "grade": g, "rows": n}
            for y, s, g, n in connection.execute(
                "SELECT year, semester, grade, COUNT(*) FROM courses "
                "GROUP BY year, semester, grade ORDER BY year, semester, grade"
            )
        ],
        "departments": [
            r[0]
            for r in connection.execute(
                "SELECT DISTINCT dept FROM courses ORDER BY dept"
            )
        ],
    }


def import_courses(paths, database, key_path=Path("data/.professor-key")):
    """검증한 파일의 (학년도, 학기, 학년)만 하나의 트랜잭션으로 교체한다."""
    paths = sorted(Path(p) for p in paths)
    database, key_path = Path(database), Path(key_path)
    if not paths:
        raise ImportValidationError("적재할 .xlsx 파일이 없습니다.")
    if database.resolve() == key_path.resolve():
        raise ImportValidationError("DB와 가명 키 경로는 달라야 합니다.")
    key = _load_key(key_path, database.exists())
    batches = {}
    course_keys = set()
    for index, path in enumerate(paths, 1):
        try:
            period, courses = read_courses(path, key)
            if period in batches:
                raise ImportValidationError(
                    "같은 학년도·학기·학년 파일이 중복되었습니다."
                )
            for row in courses:
                course_key = row[0], row[1], row[4]
                if course_key in course_keys:
                    raise ImportValidationError(
                        "학년 파일 간 강좌번호가 중복되었습니다."
                    )
                course_keys.add(course_key)
            batches[period] = courses
        except ImportValidationError as exc:
            raise ImportValidationError(f"입력 파일 {index}: {exc}") from None
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(CREATE_COURSES)
            connection.execute(
                "CREATE TABLE IF NOT EXISTS import_metadata "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            fingerprint = hashlib.sha256(key).hexdigest()
            previous = connection.execute(
                "SELECT value FROM import_metadata WHERE key = 'pseudonym_key'"
            ).fetchone()
            if previous and previous[0] != fingerprint:
                raise ImportValidationError("기존 DB와 가명 키가 다릅니다.")
            if (
                not previous
                and connection.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
            ):
                raise ImportValidationError("가명 키를 확인할 수 없는 기존 DB입니다.")
            connection.execute(
                "INSERT OR IGNORE INTO import_metadata VALUES ('pseudonym_key', ?)",
                (fingerprint,),
            )
            for period in batches:
                connection.execute(
                    "DELETE FROM courses WHERE year=? AND semester=? AND grade=?",
                    period,
                )
            for courses in batches.values():
                connection.executemany(
                    f"INSERT INTO courses ({', '.join(COLUMNS)}) "
                    f"VALUES ({', '.join('?' for _ in COLUMNS)})",
                    courses,
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS courses_dept ON courses(dept, year, semester)"
            )
            result = database_summary(connection)
        return {
            "imported_files": len(batches),
            "imported_rows": sum(len(rows) for rows in batches.values()),
            **result,
        }
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description="개설강좌 엑셀 검증·가명 처리·SQLite 적재"
    )
    parser.add_argument(
        "files", nargs="*", type=Path, help="생략하면 data/*.xlsx 전체 적재"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path(os.environ.get("COURSE_DB_PATH", "data/courses.sqlite3")),
    )
    args = parser.parse_args()
    try:
        result = import_courses(args.files or Path("data").glob("*.xlsx"), args.db)
    except ImportValidationError as exc:
        parser.exit(1, f"적재 중단: {exc}\n")
    except Exception:
        # 라이브러리 예외에는 원본 셀 값·경로가 포함될 수 있다.
        parser.exit(
            1, "적재 중단: 파일 또는 DB 처리 오류입니다. 형식·권한을 확인해 주세요.\n"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
