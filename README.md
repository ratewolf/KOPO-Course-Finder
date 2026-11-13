# KOPO Course Finder

한국어 자연어 질문으로 **한국폴리텍대학 서울정수캠퍼스의 역대 개설강좌를 조회**하는 프로젝트입니다. Text-to-SQL 모델로 질문을 SQL로 변환하고, 데이터베이스에서 조회한 결과를 표와 실행한 SQL로 보여주는 것을 목표로 합니다.

> 현재 공통 GPU 개발 환경을 준비한 단계입니다. 강좌 조회 앱은 아직 구현 전이며, 아래 서비스 기능은 구현 계획입니다.

## 프로젝트 배경

학기·학년별로 나뉜 개설강좌 스프레드시트에서 여러 학기의 강좌를 비교하려면 파일을 하나씩 열어 확인해야 합니다. 이 프로젝트는 해당 자료를 하나의 관계형 데이터베이스로 모아, SQL을 모르는 사용자도 질문으로 필요한 강좌를 찾을 수 있도록 합니다.

수강신청을 앞둔 재학생과 학과의 교육과정을 미리 확인하고 싶은 입학 예정자·신입생을 주요 사용자로 생각하고 있습니다.

## 질문 예시

- "2025년 1학기 인공지능소프트웨어과 2학년 강좌를 보여줘."
- "과목명에 '파이썬'이 들어가는 강좌를 찾아줘."
- "2025년 1학기 학과별 강좌 수를 알려줘."
- "2025년 1학기 학과별 서로 다른 과목 수를 알려줘."
- "연도별 NCS 강좌 비율을 보여줘."

조회 가능한 학년도·학기와 학과는 실제 적재된 자료를 기준으로 안내할 예정입니다.

## 구현할 기능

| 구분 | 기능 | 내용 |
| --- | --- | --- |
| 필수 | 데이터 적재 | 개설강좌 `.xlsx` 파일의 형식을 확인하고 정제·가명 처리한 뒤 SQLite에 적재 |
| 필수 | 자연어 강좌 조회 | 한국어 질문을 SQL로 변환하고 검증 후 실행하여 결과 표 표시 |
| 필수 | 실행한 SQL 확인 | 조회에 사용한 SQL을 화면에서 확인 |
| 필수 | 예시 질문과 결과 안내 | 예시 질문 버튼, 조회 건수 요약, 처리 상태 및 오류 안내 |
| 선택 | Gemini 보충 설명 | 사용자가 API 키를 입력하면 조회 결과에 대한 해설 제공 |
| 선택 | 강좌 도우미 | 검색 기록과 이전 결과에 대한 후속 질문 지원 |
| 선택 | 결과 다운로드 | 조회 결과를 CSV로 저장 |

Gemini 연동은 선택 기능으로 설계합니다. API 키가 없거나 외부 API 호출이 실패해도 기본 조회와 로컬 템플릿 요약을 사용할 수 있도록 구현할 예정입니다.

## 처리 흐름

```text
개설강좌 엑셀 파일
    └─ 형식 확인 → 정제·가명 처리 → SQLite 적재

한국어 질문
    ↓
입력 확인 및 프롬프트 구성
(질문 + DB 스키마 + 한국어 컬럼 설명 + 수집 범위 + 학과명 목록)
    ↓
로컬 Text-to-SQL 모델로 SQL 생성
    ↓
SQLGlot 검증 → 읽기 전용 SQLite 조회
    ↓
결과 표 + 실행한 SQL + 로컬 요약
    └─ 선택: Gemini로 결과 보충 설명
```

모델은 greedy decoding으로 SQL 생성의 무작위성을 줄이고, 조회 결과의 근거가 되는 SQL을 화면에 표시할 계획입니다. 다만 실행 가능한 SQL도 질문의 의도와 다를 수 있으므로, 평가 질문과 정답 SQL로 조회 정확도를 검증할 예정입니다.

## 기술 구성 계획

| 역할 | 기술 |
| --- | --- |
| 개발 언어 | Python |
| 기반 모델 | `unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit` |
| 한국어 SQL LoRA 어댑터 | `huggingface-KREW/Llama-3.1-8B-Spider-SQL-Ko` |
| 모델 실행 | PyTorch, Transformers, PEFT, bitsandbytes를 이용한 4bit 추론 |
| 데이터 적재 | openpyxl, SQLite |
| SQL 검증 | SQLGlot |
| 조회 화면 및 서버 | Gradio |
| 접속용 화면 | HTML/JavaScript, `@gradio/client`, Hugging Face Static Space |
| 선택적 결과 해설 | Gemini API |
| 개발·실행 환경 | Docker, 로컬 NVIDIA GPU 환경 |

기반 모델은 SQL 어댑터의 [adapter_config.json](https://huggingface.co/huggingface-KREW/Llama-3.1-8B-Spider-SQL-Ko/blob/11d1e533ccbe48c9135baeba83a16205ca4ca251/adapter_config.json)에 지정된 사전 양자화 모델을 사용합니다. Unsloth 라이브러리는 별도로 설치하지 않고 Transformers와 PEFT로 불러올 계획입니다.

## 공통 개발 환경

실습실의 Windows + WSL2 + Docker Desktop + RTX 3080 10GB 환경을 기준으로 합니다. 컨테이너는 Linux x86_64, Python 3.11.14, PyTorch 2.6.0 + CUDA 12.4를 사용합니다.

- Docker 빌드·GPU 설정·볼륨·포트는 **`compose.yaml` 하나**에서 관리합니다. 별도 Dockerfile이나 CPU/GPU 오버라이드 파일은 사용하지 않습니다.
- Python의 실행·GPU 추론·개발 도구 의존성은 **`requirements.txt` 하나**에서 관리합니다. 상단에는 직접 사용하는 패키지를 용도별로, 하단에는 전이 의존성을 고정해 정리합니다.
- `.dockerignore`는 빌드에 `requirements.txt`만 허용합니다. 소스와 로컬 데이터는 실행 시 작업 폴더를 연결해 사용합니다.
- `.env`는 필요한 설정을 바꿀 때 사용하며, API 키는 포함하지 않습니다.

빌드 정의를 Compose에 넣는 방식은 [Docker Compose의 `dockerfile_inline`](https://docs.docker.com/reference/compose-file/build/#dockerfile_inline)을 사용하므로 Compose 2.17 이상이 필요합니다. Docker Desktop은 WSL2 기반 Linux 컨테이너와 GPU 지원이 활성화되어 있어야 합니다.

### VS Code에서 개발하기

1. Docker Desktop을 실행하고 VS Code에 [Dev Containers 확장](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)을 설치합니다.
2. VS Code에서 이 저장소 폴더를 엽니다.
3. `Ctrl+Shift+P` → **Dev Containers: Reopen in Container**를 실행합니다.
4. 컨테이너 준비와 확장 설치가 끝나면 통합 터미널에서 개발합니다. Python은 `/usr/local/bin/python`을 사용하며, 호스트 Python이나 별도 가상 환경은 필요하지 않습니다.

`.devcontainer/devcontainer.json`은 기존 `compose.yaml`의 `app` 서비스를 사용합니다. GPU·작업 폴더·모델 캐시·포트 설정도 동일하게 적용됩니다. Python, Pylance, Python Debugger, Ruff, EditorConfig 확장을 자동 설치하고, Python 파일 저장 시 컨테이너에 설치한 Ruff로 포맷·수정·import 정리를 수행합니다. 컨테이너를 처음 만들 때는 `pip check`로 설치 상태를 확인합니다.

실습실에 설치된 Dev Containers CLI 0.90은 `dockerfile_inline`을 직접 해석하지 못하므로, 연결 전에 루트 Compose 파일로 이미지를 빌드하고 `.devcontainer/compose.yaml`이 해당 이미지를 사용하도록 연결합니다. 빌드 내용과 GPU·볼륨·포트 정의는 루트 `compose.yaml`에서 관리하며, VS Code용 파일에는 이미지 연결 설정만 둡니다. 기존 이미지와 빌드 캐시를 재사용합니다.

연결된 VS Code 터미널에서는 `python`, `ruff` 등을 바로 실행합니다. VS Code 창을 닫으면 해당 Compose 서비스를 중지하며, 작업 파일과 모델 캐시는 유지됩니다. `requirements.txt`나 컨테이너 설정을 변경한 뒤에는 **Dev Containers: Rebuild Container**로 반영합니다. 앱 실행과 브라우저 접속 방법은 아래와 같습니다.

### 환경 시작

저장소 루트에서 실행합니다. 별도 설정이 없으면 `.env` 없이도 기본값을 사용합니다. 기존 `.env`가 있다면 새 `.env.example`의 설정과 비교해 필요한 항목만 갱신합니다.

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose exec app bash
```

새 로컬 설정 파일이 필요한 경우에만 `.env.example`을 `.env`로 복사합니다. 기존 `.env`는 덮어쓰지 않습니다.

현재 컨테이너는 개발 작업을 위해 대기하며, 웹 서버를 자동 실행하지 않습니다. 향후 `app.py`를 구현한 뒤 다음 명령으로 실행할 예정입니다.

```powershell
docker compose exec app python app.py
```

실행 후 접속 주소는 `http://127.0.0.1:7860`입니다. 호스트에는 루프백 주소로만 포트를 열고, 컨테이너 내부의 Gradio는 `0.0.0.0:7860`에서 연결을 받도록 설정했습니다.

### 환경 확인과 종료

```powershell
docker compose exec app python -m pip check
docker compose exec app python -c "import torch; print(torch.__version__, torch.version.cuda); print(torch.cuda.get_device_name(0))"
docker compose exec app ruff check .
docker compose down
```

의존성을 변경했을 때는 이미지를 다시 빌드합니다. Python 소스 수정은 연결된 작업 폴더에 바로 반영되며, 실행 중인 앱의 재시작은 별도로 필요합니다. Hugging Face 모델 캐시는 이름 있는 볼륨에 보관되므로 일반적인 `docker compose down` 후에도 유지됩니다.

현재 환경에서 이미지 빌드, `pip check`, GPU 인식, 작은 NF4 4bit 연산, Gradio·Gemini SDK import와 모델 캐시 쓰기를 확인했습니다. 기반 모델과 SQL 어댑터의 리비전은 설정에 고정했으며, 모델 가중치 다운로드와 실제 8B 모델의 VRAM·생성 품질 검증은 다음 개발 단계에서 진행합니다. Gemini API 키는 향후 화면에서 입력받으며 로컬 환경 파일에는 저장하지 않습니다.

## 데이터 설계

한국폴리텍대학 서울정수캠퍼스 학생정보시스템에서 제공하는 개설강좌 엑셀 자료를 입력으로 사용합니다. 학년도와 학기는 파일명에서 추출하고, 학년 등 필요한 값은 자료형을 정리해 적재할 계획입니다. 파일에 포함된 총건수 요약 행은 강좌 데이터에서 제외합니다.

### `courses` 테이블 초안

모델에 전달할 스키마는 영어 이름을 사용하고, 프롬프트에 한국어 설명을 함께 제공합니다.

| 컬럼 | 의미 |
| --- | --- |
| `year` | 학년도 |
| `semester` | 학기 |
| `grade` | 학년 |
| `is_ncs` | NCS 여부 (`Y` / `N`) |
| `course_no` | 분반별 강좌 번호 |
| `dept` | 학과 |
| `major` | 전공 |
| `day_night` | 주간·야간 구분 |
| `subject_code` | 과목코드 |
| `subject_name` | 과목명 |
| `section` | 수강반 |
| `professor` | 가명 처리한 교수명 |

### 집계 기준과 조회 범위

- **강좌 수**는 분반을 포함한 행 수인 `COUNT(*)`로 집계합니다.
- **과목 수**는 중복 과목코드를 제외한 `COUNT(DISTINCT subject_code)`로 집계합니다.
- 학점, 교양·전공 구분, 수강 인원, 강의 시간, 강의실은 원본 자료에 없어 조회 대상에서 제외합니다. `major`는 전공명으로, 교양·전공 구분을 뜻하지 않습니다.
- 자료에 없는 항목이나 수집 범위 밖의 기간을 질문하면 조회 가능한 범위를 안내하도록 설계합니다.

## SQL 실행 및 개인정보 처리 방침

다음 제한을 구현할 계획입니다.

- SQLGlot로 단일 `SELECT` 조회인지 확인하고, 허용된 테이블과 함수만 사용하도록 제한합니다.
- 데이터베이스에 읽기 전용으로 연결하고, 실행 시간·계산량을 제한하며 결과는 최대 200행까지 표시합니다.
- SQL 검증 실패 시 한 번 재생성하고, 재시도에도 실패하면 안내 문구를 표시합니다.
- 교직원번호는 교수명 가명 처리 과정에서만 사용하고 조회 DB에 저장하지 않습니다.
- 교수명은 가명으로 변환하며, 원본 엑셀과 가명 대응표는 공개 저장소 및 배포 파일에서 제외합니다.
- Gemini API 키는 화면에서 가려서 입력받고, DB·코드·로그에 저장하지 않도록 처리합니다.
- Gemini에는 가명 처리한 조회 결과의 일부만 전달하도록 제한합니다.

## 배포 구상

접속용 정적 화면과 모델 조회 서버를 분리하는 구성을 계획하고 있습니다.

```text
사용자 브라우저
    ↓
Hugging Face Static Space
(조회 서버 주소 입력, 접속용 화면)
    ↓ @gradio/client
별도 GPU 서버의 Docker 컨테이너
(Gradio + Text-to-SQL 모델 + SQLGlot + SQLite)
    └─ 선택: Gemini API
```

Static Space에는 접속용 화면을 두고 모델과 DB는 별도 서버에서 실행합니다. 브라우저에서 해당 서버에 접근할 수 있어야 하며, CORS와 로컬 네트워크 접근 등 연결 조건은 구현 과정에서 확인할 예정입니다. Gradio 화면에 직접 접속하는 방식도 준비할 계획입니다.

## 개발 목표

현재 준비한 환경을 바탕으로 다음 순서로 구현합니다.

| 순서 | 작업 | 완료 기준 |
| --- | --- | --- |
| 1 | 엑셀 적재·가명 처리 | 입력 양식·건수·중복을 확인하고 개인정보를 제외한 DB 생성 |
| 2 | 모델 추론 확인 | 고정한 기반 모델과 어댑터로 한국어 질문에서 SQL 생성, VRAM·지연 측정 |
| 3 | 안전한 조회 연결 | 허용된 SQL만 읽기 전용으로 실행하고 시간·행 수 제한 적용 |
| 4 | Gradio 화면 구현 | 질문 입력부터 결과 표·SQL·오류 안내까지 연결 |
| 5 | 브라우저 접속 검증 | 최소 화면으로 Static Space → 조회 서버 연결 조건 확인 |
| 6 | 선택 기능과 품질 개선 | Gemini 해설·CSV·후속 질문을 추가하고 평가 질문셋으로 정확도 확인 |

모델 구동과 브라우저 연결은 실패 시 설계에 영향을 주므로, 데이터 적재를 진행하는 동안 작은 예제로 먼저 확인할 계획입니다.

- [ ] 엑셀 정제·가명 처리 및 SQLite 적재
- [ ] 로컬 모델의 4bit 구동 확인
- [ ] 질문 → SQL 생성 → 검증 → 조회 파이프라인 구현
- [ ] Gradio 화면과 입력·오류 안내 구현
- [ ] 평가 질문셋으로 조회 정확도 검증
- [ ] Static Space와 별도 조회 서버 연결 검증
- [ ] 선택 기능 구현: Gemini 해설, 후속 질문, CSV 다운로드
- [ ] 설치·실행 절차 및 배포 안내 추가

## 저장소 기본 설정

| 파일 | 용도 |
| --- | --- |
| `.gitignore` | 내부 문서(`docs/`), 원본 자료(`data/`, 엑셀 파일), 로컬 DB·모델·환경 설정·로그를 Git 추적 대상에서 제외 |
| `.gitattributes` | 텍스트 파일의 줄바꿈을 LF로 통일하고 Windows 명령 스크립트는 CRLF 사용 |
| `.editorconfig` | UTF-8 인코딩, 들여쓰기, 줄바꿈 등 편집 규칙 공유 |
| `.env.example` | DB 경로, 모델 리비전, 추론·SQL 제한, 접속 포트 등 환경 변수 예시 |
| `compose.yaml` | 공통 GPU 개발 환경의 빌드·실행 설정 |
| `requirements.txt` | Python 실행·GPU·개발 도구 의존성의 단일 목록 |
| `.dockerignore` | Docker 빌드에 필요한 파일만 허용 |
| `.devcontainer/devcontainer.json` | VS Code에서 공통 GPU 컨테이너에 연결하고 Python·Ruff 편집 환경 구성 |
| `.devcontainer/compose.yaml` | Dev Containers에서 인라인 빌드 대신 준비된 개발 이미지를 사용하도록 연결 |

Compose가 `.env`의 지정된 설정을 컨테이너 환경 변수로 전달합니다. 모델 추론과 SQL 제한 등 앱 설정은 향후 실행 코드에서 읽도록 구현할 예정이며, `.env`는 Git에서 제외됩니다.

## 참고 자료

- [한국어 Text-to-SQL 어댑터](https://huggingface.co/huggingface-KREW/Llama-3.1-8B-Spider-SQL-Ko)
- [한국어 Spider 데이터셋](https://huggingface.co/datasets/huggingface-KREW/spider-ko)
- [Hugging Face Spaces 문서](https://huggingface.co/docs/hub/en/spaces-overview)
- [Gradio 문서](https://www.gradio.app/docs)
- [SQLGlot 저장소](https://github.com/tobymao/sqlglot)
- [Gemini API 문서](https://ai.google.dev/gemini-api/docs)
