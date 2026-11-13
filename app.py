"""기존 Compose 환경에서 Gradio 조회 앱을 시작한다."""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

from kopo_course_finder.config import Settings
from kopo_course_finder.conversation import ConversationService, GeminiRewriter
from kopo_course_finder.data import database_summary
from kopo_course_finder.service import QueryService
from kopo_course_finder.ui import build_app


def main():
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
    app.queue(max_size=20).launch(
        show_error=False,
        show_api=False,
        share=True,
        blocked_paths=[
            str(root / name)
            for name in ("data", "docs", "outputs", ".env", ".git", ".cache")
        ],
    )


if __name__ == "__main__":
    main()
