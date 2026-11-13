"""기존 Static Space에 공개 프런트엔드 파일만 업로드한다."""

from pathlib import Path

from huggingface_hub import HfApi


def main():
    api = HfApi()
    repo_id = "wwgs2005/KOPO-Course-Finder"
    info = api.space_info(repo_id)
    if info.sdk != "static":
        raise SystemExit("대상 Space SDK가 static이 아닙니다. 업로드를 중단합니다.")
    result = api.upload_folder(
        repo_id=repo_id,
        repo_type="space",
        folder_path=Path(__file__).resolve().parents[1] / "static",
        allow_patterns=[
            "README.md",
            "index.html",
            "style.css",
            "app.js",
            "polytech_logo.svg",
        ],
        commit_message="Update course finder static client",
        parent_commit=info.sha,
    )
    print(result.commit_url)


if __name__ == "__main__":
    main()
