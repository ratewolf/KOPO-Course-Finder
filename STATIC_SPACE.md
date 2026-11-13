# Static Space 연결과 검증

대상: https://huggingface.co/spaces/wwgs2005/KOPO-Course-Finder

접속 화면: https://wwgs2005-kopo-course-finder.static.hf.space

## 실행

기존 서버를 종료한 뒤 저장소 루트에서 실행합니다. 동일한 포트에 두 서버를 동시에 실행하지 않습니다.

```powershell
docker compose exec app python app.py --static-space
```

기본 `python app.py`는 기존 로컬 전용 실행 방식입니다. `--static-space`는 FastAPI에 Gradio를 연결하고 위의 **정확한 Static Space 출처 하나**에만 추가 CORS 권한을 줍니다. Docker·포트·의존성·`.env`는 변경하지 않습니다. 기본 루프백 바인딩을 유지하므로 인터넷에서 GPU 서버에 직접 접근할 수 없습니다. CORS는 인증 기능이 아니며 서버를 외부에 공개하는 설정도 아닙니다.

로컬 정적 화면 미리보기: http://127.0.0.1:7860/space-preview/

기존 Gradio 직접 접속: http://127.0.0.1:7860

## 배포

`static/`의 파일만 Space 저장소 루트로 올립니다. 프로젝트 루트 전체를 업로드하지 않습니다. SDK는 `static`, 진입 파일은 `index.html`이며 빌드나 패키지 설치가 필요 없습니다. 브라우저에서 jsDelivr의 버전 고정 `@gradio/client@1.17.0` 모듈을 불러오므로 CDN 접근이 필요합니다.

```powershell
docker compose exec app hf auth login
docker compose exec app python scripts/deploy_static.py
```

토큰은 채팅이나 소스 파일에 넣지 않습니다. Space 업로드에는 해당 저장소 쓰기 권한이 필요합니다. 원본 자료·DB·모델·로컬 문서·`.env`는 업로드 대상이 아닙니다.

고정 환경의 `hf upload`는 기존 저장소에도 생성 요청을 보내며 현재 Hub에서 Gradio/Docker 유료 요금 안내(402)를 반환했습니다. 배포 스크립트는 이미 존재하는 Space의 `sdk: static`을 확인한 뒤 `HfApi.upload_folder`로 직접 업로드합니다. 저장소 생성이나 유료 리소스 요청은 하지 않으며, 직전 커밋을 지정해 동시 변경을 덮어쓰지 않습니다.

## 사용과 검증 순서

1. GPU 서버가 실행된 **같은 PC**의 브라우저에서 Space를 엽니다. Hugging Face 페이지 안의 iframe에서 막히면 위의 접속 화면 주소를 별도 탭으로 엽니다.
2. 서버 주소 `http://127.0.0.1:7860`으로 연결합니다. 이 주소는 항상 방문자 자신의 PC입니다. 다른 사람의 PC에서는 개발자의 서버를 가리키지 않습니다.
3. 브라우저가 로컬 네트워크 접근 권한을 요청하면 사용자가 해당 사이트를 확인하여 허용합니다. 브라우저 보안 기능을 전체 비활성화하지 않습니다.
4. 전체 강좌 수 → 7,507, `파이썬` 검색 → 9행을 확인합니다. SQL·원문·결과 안내를 비교합니다.
5. Gemini 키는 연결된 서버 주소를 확인한 뒤 직접 입력합니다. 키 적용 후 첫 조건 조회와 후속 질문을 실행합니다. 키는 연결 서버 세션 메모리에만 보관되며 브라우저 저장소에 저장하지 않습니다. 원본/재작성 질문 및 API 호출 횟수를 확인합니다.
6. 초기화, 키 해제, 연결 해제, 새 연결의 세션 분리를 확인합니다. 조회 실패 시 기존 표를 새 결과로 오인하지 않도록 안내를 확인합니다.

화면 새로고침·재연결은 새 클라이언트 세션입니다. 기존 Gradio 화면에서 입력한 키나 기록은 Static Space로 자동 이전되지 않습니다. 연결 해제 시 키 해제를 시도하며, 탭 종료 시 클라이언트 연결을 닫습니다. 네트워크 단절 등으로 종료 요청이 전달되지 않으면 서버의 세션 만료 정리가 적용됩니다.

## 연결 실패 구분

| 증상 | 확인 |
| --- | --- |
| 직접 접속도 실패 | 컨테이너·모델 로딩·앱 프로세스·7860 포트 |
| 직접 접속 성공, Space 연결 실패 | `--static-space` 실행 여부, 정확한 Space 출처, 브라우저 로컬 네트워크 권한 |
| Hugging Face 내에서만 실패 | 별도 탭의 `.static.hf.space` 주소로 재검증; iframe 권한 정책 차이 가능 |
| 연결은 성공하나 키/초기화 실패 | 서버에 `/set_key`, `/release_key`, `/reset` API가 있는 최신 앱인지 확인 |
| 후속 질문만 실패 | 같은 Space 세션에 키를 적용했는지, 오류 안내와 Gemini 호출 상태 확인 |

불특정 출처 허용, `strict_cors=False`, 포트 공개, 터널 설치는 적용하지 않습니다. 브라우저 정책으로 연결할 수 없으면 기존 로컬 Gradio 화면에서 시연합니다.

## 검증 기록 (2026-11-13)

- 공개 Space가 `sdk: static`이고 초기 템플릿 상태임을 확인했습니다.
- 사용자 승인 후 `--static-space` 모드로 서버를 실행했습니다.
- 지정 출처의 GET 응답 CORS 허용과 POST preflight 200을 확인했습니다. 임의 외부 출처에는 허용 헤더가 없습니다.
- 로컬 정적 미리보기에서 JavaScript 클라이언트 연결, 전체 COUNT 7,507, 파이썬 검색 9행과 SQL, 완료 후 버튼 복구, 초기화, 가짜 테스트 값의 키 적용·해제를 확인했습니다. 테스트 키로 Gemini를 호출하지 않았습니다.
- Static Space에 정적 파일 5개를 업로드하고 HTTPS에서 화면 로딩을 확인했습니다. 최초 배포 커밋: `33f14ecc8effaf4e30014f94905b9633b20eb11a`.
- 사용자가 Chrome에서 HTTPS Space → 로컬 서버 연결 성공을 확인했습니다. 자동 검증용 앱 내 브라우저는 같은 연결에서 대기 상태였으므로 해당 브라우저 성공을 주장하지 않습니다. 권한 대기로 계속 잠기지 않도록 연결에 20초 제한을 추가했습니다.
- Chrome 추가 자동 조작은 도구가 현재 URL을 확실히 식별하지 못해 중단했습니다. Chrome의 실제 Space 화면에서 질문 → 표 표시 및 Gemini 연속 질문은 사용자 확인이 남아 있습니다. 기존 로컬 Gradio에서 Gemini 실제 키 성공은 사용자가 별도로 확인한 결과입니다.

참고: [Static HTML Spaces](https://huggingface.co/docs/hub/en/spaces-sdks-static), [Gradio JS Client](https://www.gradio.app/docs/js-client).
