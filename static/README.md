---
title: KOPO Course Finder
emoji: 🎓
colorFrom: blue
colorTo: red
sdk: static
app_file: index.html
pinned: false
---

# KOPO Course Finder

한국폴리텍대학 서울정수캠퍼스 개설강좌 조회 접속 화면입니다.
모델과 데이터베이스는 사용자의 별도 Gradio 서버에서 실행됩니다.
기본 주소 `http://127.0.0.1:7860`은 방문자 본인의 컴퓨터를 가리킵니다.
서버가 실행 중이어야 하며 브라우저의 로컬 네트워크 접근 허용이 필요할 수 있습니다.

API 키는 입력한 조회 서버에 전달되어 세션 메모리에만 보관됩니다.
본인이 실행했거나 신뢰하는 서버에만 연결하세요.
브라우저가 연결을 차단하면 로컬 Gradio 화면으로 직접 접속할 수 있습니다.
