"""기존 Compose 환경에서 Gradio 조회 앱을 시작한다."""

import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import gradio as gr
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from kopo_course_finder.config import Settings
from kopo_course_finder.conversation import ConversationService, GeminiRewriter
from kopo_course_finder.data import database_summary
from kopo_course_finder.service import QueryService
from kopo_course_finder.ui import build_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--static-space",
        action="store_true",
        help="지정된 KOPO Static Space 출처에만 브라우저 연결을 허용합니다.",
    )
    args = parser.parse_args()
    settings = Settings.from_env()
    with closing(
        sqlite3.connect(settings.database.resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        metadata = database_summary(db)
    service = QueryService(settings)
    print("로컬 SQL 모델을 준비하고 있습니다.", flush=True)
    service.model.load()
    conversation = ConversationService(
        service, GeminiRewriter(os.getenv("GEMINI_MODEL", ""))
    )
    app = build_app(conversation, metadata)
    root = Path(__file__).resolve().parent
    blocked = [
        str(root / name)
        for name in ("data", "docs", "outputs", ".env", ".git", ".cache")
    ]
    app.queue(max_size=20)
    if args.static_space:
        server = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        server.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "https://wwgs2005-kopo-course-finder.static.hf.space",
            ],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type"],
            allow_credentials=True,
        )
        server.mount(
            "/space-preview", StaticFiles(directory=root / "static", html=True)
        )
        server = gr.mount_gradio_app(
            server,
            app,
            path="/",
            blocked_paths=blocked,
            show_api=False,
            show_error=False,
        )
        uvicorn.run(
            server,
            host=os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"),
            port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
            access_log=False,
        )
        return
    app.launch(
        show_error=False,
        show_api=False,
        share=False,
        blocked_paths=blocked,
    )


if __name__ == "__main__":
    main()
