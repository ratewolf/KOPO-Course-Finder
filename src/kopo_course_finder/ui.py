"""Gradio 조회 화면. 데이터 적재·파일·키 조회 API는 노출하지 않는다."""

import threading

import gradio as gr
import pandas as pd

from .conversation import Session


def build_app(conversation, metadata):
    sessions = {}
    registry_lock = threading.Lock()

    def dispose(session):
        if not isinstance(session, Session):
            return
        with registry_lock:
            sessions.pop(session.session_id, None)
        session.reset(release_key=True)

    def register(session, request):
        if session is None:
            session = Session()
        if request.session_hash:
            session.session_id = request.session_hash
            with registry_lock:
                sessions[request.session_hash] = session
        return session

    def unload(request: gr.Request):
        with registry_lock:
            session = sessions.pop(request.session_hash, None)
        if session is not None:
            session.reset(release_key=True)

    def submit(
        question, new_query, session, request: gr.Request, progress=gr.Progress()
    ):
        session = register(session, request)
        yield (
            session,
            session.history,
            "질문을 확인하고 있습니다…",
            question,
            "",
            gr.skip(),
            gr.skip(),
            "처리 중",
        )
        try:
            turn = conversation.ask(
                session,
                question,
                new_query=new_query,
                on_stage=lambda text: progress(0.5, desc=text),
            )
        except Exception:
            # 외부 SDK·개발 예외의 세부 내용은 화면/로그에 노출하지 않는다.
            yield (
                session,
                session.history,
                "처리하지 못했습니다. 잠시 후 다시 시도해 주세요.",
                question,
                "",
                gr.skip(),
                gr.skip(),
                "처리 오류",
            )
            return
        if turn.status == "cancelled":
            return
        if turn.result is None:
            frame, sql = gr.skip(), gr.skip()
            message = turn.message
            if session.last:
                message += "\n아래 표와 SQL은 마지막으로 성공한 조회 결과입니다."
        else:
            frame = pd.DataFrame(turn.result.rows, columns=turn.result.columns)
            sql = turn.result.sql
            message = turn.message
        yield (
            session,
            session.history,
            message,
            turn.original,
            turn.question,
            frame,
            sql,
            f"상태: {turn.status} · 이번 질문 Gemini 호출: {turn.api_calls}회",
        )

    def set_key(value, session, request: gr.Request):
        session = register(session, request)
        value = value.strip()
        if not value or len(value) > 512:
            return session, "", "키를 올바르게 입력해 주세요."
        session.api_key = value
        return (
            session,
            "",
            "키를 세션 메모리에 보관했습니다. 실제 호출 시 유효성을 확인합니다.",
        )

    def release_key(session, request: gr.Request):
        session = register(session, request)
        session.api_key = ""
        return session, "", "키를 해제했습니다. 독립 질문은 계속 조회할 수 있습니다."

    def reset(session, request: gr.Request):
        session = register(session, request)
        session.reset()
        return (
            session,
            [],
            "대화와 결과를 초기화했습니다.",
            "",
            "",
            pd.DataFrame(),
            "",
            "준비",
            "",
            False,
        )

    years = sorted({row["year"] for row in metadata["coverage"]})
    coverage = ", ".join(map(str, years)) or "없음"
    examples = [
        "2025년 1학기 인공지능소프트웨어과 2학년 강좌를 보여줘.",
        "과목명에 '파이썬'이 들어가는 강좌를 찾아줘.",
        "2025년 1학기 학과별 강좌 수를 알려줘.",
        "연도별 NCS 강좌 비율을 보여줘.",
    ]
    with gr.Blocks(
        title="KOPO Course Finder", theme=gr.themes.Soft(), analytics_enabled=False
    ) as app:
        state = gr.State(value=Session(), time_to_live=1800, delete_callback=dispose)
        gr.Markdown(
            "# KOPO Course Finder\n서울정수캠퍼스 개설강좌를 질문으로 찾아보세요."
        )
        gr.Markdown(
            f"**수집 학년도:** {coverage} · **강좌:** {metadata['rows']:,}개\n\n"
            "강좌는 분반 단위이며 교수명은 가명입니다. 학점·수강 인원·시간·강의실은 조회할 수 없습니다."
        )
        with gr.Accordion("조회 가능한 학과와 사용 방법", open=False):
            gr.Markdown(" · ".join(metadata["departments"]))
            gr.Markdown(
                "연도·학기·학과를 함께 입력하면 더 정확합니다. 과목명 검색어는 따옴표로 감싸 주세요.\n\n"
                "독립 질문에는 API 키가 필요하지 않습니다. 후속 질문은 마지막 성공 조회를 기준으로 해석합니다. "
                "확인 질문에 답하는 중 새 검색을 하려면 ‘새 조회’를 선택하세요."
            )
        with gr.Accordion("Gemini 후속 질문 설정", open=False):
            gr.Markdown(
                "후속 질문 해석 시 현재 질문과 마지막 성공 질문·SQL·결과 메타데이터가 Google로 전송됩니다. "
                "전체 결과 표와 원본 엑셀은 전송하지 않습니다. 키는 파일에 저장하지 않습니다."
            )
            key = gr.Textbox(label="Gemini API 키", type="password", max_length=512)
            with gr.Row():
                apply_key = gr.Button("키 적용")
                remove_key = gr.Button("키 해제")
            key_status = gr.Textbox(
                label="키 상태",
                value="키가 없습니다. 독립 질문은 조회할 수 있습니다.",
                interactive=False,
            )
        question = gr.Textbox(
            label="질문",
            placeholder="2025년 인공지능소프트웨어과의 모든 개설강좌를 알려줘.",
            lines=2,
            max_length=2000,
        )
        gr.Examples(
            examples=[[value] for value in examples],
            inputs=question,
            cache_examples=False,
        )
        with gr.Row():
            new_query = gr.Checkbox(label="새 조회 (이전 조건 사용 안 함)", value=False)
            run = gr.Button("조회", variant="primary")
            clear = gr.Button("대화 및 결과 초기화")
        status = gr.Textbox(label="처리 상태", value="준비", interactive=False)
        message = gr.Textbox(label="결과 안내", interactive=False, lines=3)
        with gr.Row():
            original = gr.Textbox(label="사용자 원문", interactive=False)
            rewritten = gr.Textbox(label="SQL 모델에 전달한 질문", interactive=False)
        table = gr.Dataframe(
            label="조회 결과",
            interactive=False,
            wrap=True,
            show_copy_button=True,
            max_height=420,
        )
        with gr.Accordion("실행한 SQL", open=False):
            sql = gr.Code(language="sql", label="SQL", interactive=False)
        history = gr.Chatbot(
            label="검색 기록",
            type="messages",
            height=300,
            sanitize_html=True,
            render_markdown=False,
            allow_file_downloads=False,
        )
        outputs = [state, history, message, original, rewritten, table, sql, status]
        event = gr.on(
            triggers=[run.click, question.submit],
            fn=submit,
            inputs=[question, new_query, state],
            outputs=outputs,
            api_name="query",
            concurrency_limit=1,
            concurrency_id="course_queries",
            trigger_mode="once",
        )
        apply_key.click(
            set_key, [key, state], [state, key, key_status], api_name=False, queue=False
        )
        remove_key.click(
            release_key, [state], [state, key, key_status], api_name=False, queue=False
        )
        gr.on(
            triggers=[clear.click, history.clear],
            fn=reset,
            inputs=[state],
            outputs=outputs + [question, new_query],
            cancels=[event],
            api_name=False,
            queue=False,
        )
        app.unload(unload)
    return app
