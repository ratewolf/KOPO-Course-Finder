"""고정된 4bit 기반 모델과 LoRA의 로컬 추론. import 시 로딩하지 않는다."""

import re
import threading
import time
from dataclasses import dataclass

from .schema import COLUMNS


class ModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class Generation:
    sql: str
    seconds: float
    input_tokens: int
    output_tokens: int
    peak_vram_bytes: int


def build_prompt(question, coverage, departments, correction=None):
    periods = sorted({(r["year"], r["semester"]) for r in coverage})
    schema = "테이블: courses\n컬럼:\n" + "\n".join(
        f"- {name}: {description}" for name, description in COLUMNS.items()
    )
    rules = (
        "SQLite의 단일 SELECT SQL만 출력하세요. 설명과 마크다운은 제외하세요. "
        "강좌 수는 COUNT(*), 서로 다른 과목 수는 COUNT(DISTINCT subject_code)입니다. "
        "NCS는 is_ncs = 'Y'입니다. 비율은 100.0을 곱해 실수로 계산하세요. "
        "NCS 비율 계산식은 ROUND(100.0 * SUM(CASE WHEN is_ncs = 'Y' "
        "THEN 1 ELSE 0 END) / COUNT(*), 2)입니다. "
        "연도별 집계는 GROUP BY year를 사용하며 자기 자신과 JOIN할 필요가 없습니다. "
        "과목명 키워드는 LIKE로 검색하고 한국어 검색어를 번역하지 마세요. "
        "학과 조건은 dept를 사용합니다. major는 학과가 아닌 세부 전공명입니다. "
        "강좌 목록은 SELECT *로 모든 열을 반환하세요. "
        "사용자가 요청하지 않은 LIMIT이나 조건은 추가하지 마세요. "
        "학점, 수강 인원, 강의 시간, 강의실, 교양 구분은 없습니다."
    )
    context = (
        f"\n수집 학년도·학기: {periods}\n학과명: {', '.join(departments)}\n{rules}"
    )
    # Spider 모델이 한국어 고유명사를 영어로 번역하는 오류를 줄이기 위한 값 힌트.
    literal_hints = [f"dept = '{dept}'" for dept in departments if dept in question]
    if "과목명" in question:
        literal_hints.extend(
            "subject_name LIKE '%" + word.replace("'", "''") + "%'"
            for word in re.findall(r"['\"]([^'\"]+)['\"]", question)
        )
    if literal_hints:
        context += "\n질문에 명시된 DB 조건(문자열을 번역하지 말 것): " + "; ".join(
            literal_hints
        )
    context += (
        "\n\nSQL 작성 예시 (아래 예시 조건을 현재 질문에 추가하지 마세요):"
        "\n질문: 전기과 강좌 목록\nSQL: SELECT * FROM courses WHERE dept = '전기과';"
        "\n질문: 과목명에 '기초'가 들어가는 강좌"
        "\nSQL: SELECT * FROM courses WHERE subject_name LIKE '%기초%';"
    )
    if correction:
        context += f"\n이전 생성 검증 실패: {correction} SQL을 다시 생성하세요."
    question_detail = question
    if literal_hints:
        question_detail += "\n반드시 사용할 조건: " + " AND ".join(literal_hints)
    if correction:
        question_detail += "\n반드시 수정할 사항: " + correction
    return (
        "다음 데이터베이스 스키마를 참고하여 질문에 대한 SQL 쿼리를 생성하세요.\n\n"
        f"### 데이터베이스 스키마:\n{schema}{context}\n\n"
        f"### 질문: {question_detail}\n\n### SQL 쿼리:"
    )


class LocalSQLModel:
    def __init__(self, settings):
        self.settings = settings
        self._lock = threading.Lock()
        self._model = None
        self._tokenizer = None
        self.load_seconds = None

    def load(self):
        with self._lock:
            self._load()

    def _load(self):
        if self._model is not None:
            return
        import torch
        from peft import PeftConfig, PeftModel
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer

        settings = self.settings
        if not torch.cuda.is_available():
            raise ModelError("CUDA GPU를 사용할 수 없습니다.")
        if settings.compute_dtype == "bfloat16" and not torch.cuda.is_bf16_supported():
            raise ModelError("이 GPU는 bfloat16 추론을 지원하지 않습니다.")
        start = time.monotonic()
        try:
            adapter_config = PeftConfig.from_pretrained(
                settings.adapter, revision=settings.adapter_revision
            )
            if (
                adapter_config.base_model_name_or_path.lower()
                != settings.base_model.lower()
            ):
                raise ModelError("어댑터와 기반 모델 설정이 일치하지 않습니다.")
            config = AutoConfig.from_pretrained(
                settings.base_model,
                revision=settings.base_revision,
                trust_remote_code=False,
            )
            if not config.quantization_config.get("load_in_4bit"):
                raise ModelError("기반 모델이 사전 양자화된 4bit 모델이 아닙니다.")
            config.quantization_config["bnb_4bit_compute_dtype"] = (
                settings.compute_dtype
            )
            tokenizer = AutoTokenizer.from_pretrained(
                settings.adapter,
                revision=settings.adapter_revision,
                trust_remote_code=False,
            )
            base = AutoModelForCausalLM.from_pretrained(
                settings.base_model,
                revision=settings.base_revision,
                config=config,
                dtype=getattr(torch, settings.compute_dtype),
                device_map={"": 0},
                trust_remote_code=False,
                use_safetensors=True,
            )
            model = PeftModel.from_pretrained(
                base,
                settings.adapter,
                revision=settings.adapter_revision,
                is_trainable=False,
            )
            model.eval()
            self._model, self._tokenizer = model, tokenizer
            torch.cuda.synchronize()
            self.load_seconds = time.monotonic() - start
        except ModelError:
            raise
        except Exception:
            raise ModelError(
                "모델 로딩에 실패했습니다. 캐시·GPU·고정 리비전을 확인해 주세요."
            ) from None

    def generate(self, question, coverage, departments, correction=None):
        import torch
        from transformers import GenerationConfig

        with self._lock:
            self._load()
            prompt = build_prompt(question, coverage, departments, correction)
            tokenizer = self._tokenizer
            inputs = tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
            )
            length = inputs["input_ids"].shape[-1]
            if length > self.settings.max_input_tokens:
                raise ModelError(
                    "질문과 스키마가 입력 토큰 제한을 초과했습니다. 질문을 줄여 주세요."
                )
            inputs = inputs.to("cuda:0")
            eos = [tokenizer.eos_token_id]
            eot = tokenizer.convert_tokens_to_ids("<|eot_id|>")
            if eot is not None and eot != tokenizer.unk_token_id:
                eos.append(eot)
            start = time.monotonic()
            torch.cuda.reset_peak_memory_stats()
            try:
                with torch.inference_mode():
                    output = self._model.generate(
                        **inputs,
                        generation_config=GenerationConfig(
                            do_sample=False,
                            num_beams=1,
                            max_new_tokens=self.settings.max_new_tokens,
                            max_time=self.settings.model_seconds,
                            eos_token_id=list(set(eos)),
                            pad_token_id=tokenizer.eos_token_id,
                            use_cache=True,
                        ),
                    )
                torch.cuda.synchronize()
            except Exception:
                raise ModelError(
                    "SQL 생성에 실패했습니다. GPU 상태와 질문 길이를 확인해 주세요."
                ) from None
            seconds = time.monotonic() - start
            tokens = output[0, length:]
            if seconds >= self.settings.model_seconds:
                raise ModelError("SQL 생성 시간이 초과되어 조회하지 않았습니다.")
            if not len(tokens) or tokens[-1].item() not in eos:
                raise ModelError(
                    "SQL 생성이 출력 제한 안에 완료되지 않아 조회하지 않았습니다."
                )
            text = tokenizer.decode(tokens, skip_special_tokens=True).strip()
            fenced = re.fullmatch(
                r"```(?:sql)?\s*\n?(.*?)\n?```", text, flags=re.S | re.I
            )
            if fenced:
                text = fenced[1].strip()
            return Generation(
                text, seconds, length, len(tokens), torch.cuda.max_memory_allocated()
            )
