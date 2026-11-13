"""공개 조회용 스키마. 원본의 개인 식별 필드는 저장하지 않는다."""

COLUMNS = {
    "year": "학년도",
    "semester": "학기",
    "grade": "학년",
    "is_ncs": "NCS 여부 (Y/N)",
    "course_no": "분반별 강좌 번호",
    "dept": "학과",
    "major": "전공명 (교양/전공 구분 아님)",
    "day_night": "주간/야간",
    "subject_code": "과목코드",
    "subject_name": "과목명",
    "section": "수강반",
    "professor": "가명 처리한 교수명",
}

CREATE_COURSES = """
CREATE TABLE IF NOT EXISTS courses (
    year INTEGER NOT NULL CHECK(year BETWEEN 1900 AND 2199),
    semester INTEGER NOT NULL CHECK(semester IN (1, 2)),
    grade INTEGER NOT NULL CHECK(grade IN (1, 2)),
    is_ncs TEXT NOT NULL CHECK(is_ncs IN ('Y', 'N')),
    course_no TEXT NOT NULL,
    dept TEXT NOT NULL,
    major TEXT NOT NULL,
    day_night TEXT NOT NULL CHECK(day_night IN ('주간', '야간')),
    subject_code TEXT NOT NULL,
    subject_name TEXT NOT NULL,
    section TEXT NOT NULL,
    professor TEXT NOT NULL,
    PRIMARY KEY (year, semester, course_no)
)
"""
