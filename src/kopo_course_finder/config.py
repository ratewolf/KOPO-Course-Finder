"""기존 Compose 환경 변수의 타입과 범위를 검증한다."""

import math
import os
import re
from dataclasses import dataclass
from pathlib import Path


def _number(name, default, minimum, maximum, cast=int):
    try:
        value = cast(os.environ.get(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} 설정이 숫자가 아닙니다.") from None
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} 설정은 {minimum}~{maximum} 범위여야 합니다.")
    return value


@dataclass(frozen=True)
class Settings:
    database: Path
    base_model: str
    base_revision: str
    adapter: str
    adapter_revision: str
    compute_dtype: str
    max_input_tokens: int
    max_new_tokens: int
    model_seconds: float
    max_rows: int
    sql_seconds: float

    @classmethod
    def from_env(cls):
        base_revision = os.getenv(
            "BASE_MODEL_REVISION", "f15c379fb32bb402fa06a7ae9aecb1febf4b79ec"
        )
        adapter_revision = os.getenv(
            "SQL_ADAPTER_REVISION", "11d1e533ccbe48c9135baeba83a16205ca4ca251"
        )
        if not all(
            re.fullmatch(r"[a-f0-9]{40}", r) for r in (base_revision, adapter_revision)
        ):
            raise ValueError("모델 리비전은 고정된 40자리 커밋이어야 합니다.")
        dtype = os.getenv("MODEL_COMPUTE_DTYPE", "float16")
        if dtype not in {"float16", "bfloat16"}:
            raise ValueError(
                "MODEL_COMPUTE_DTYPE은 float16 또는 bfloat16이어야 합니다."
            )
        return cls(
            Path(os.getenv("COURSE_DB_PATH", "data/courses.sqlite3")),
            os.getenv("BASE_MODEL_ID", "unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit"),
            base_revision,
            os.getenv("SQL_ADAPTER_ID", "huggingface-KREW/Llama-3.1-8B-Spider-SQL-Ko"),
            adapter_revision,
            dtype,
            _number("MODEL_MAX_INPUT_TOKENS", 2048, 128, 8192),
            _number("MODEL_MAX_NEW_TOKENS", 256, 16, 1024),
            _number("MODEL_MAX_SECONDS", 60, 1, 300, float),
            _number("MAX_RESULT_ROWS", 200, 1, 200),
            _number("SQL_TIMEOUT_SECONDS", 5, 0.01, 30, float),
        )
