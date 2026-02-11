"""
전사 JSON 파일을 DB(lecture_summary_embeddings)에 저장하는 CLI.
로그는 stderr로 출력된다.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from app.services.lecture_store import lecture_store_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="전사 JSON을 lecture_summary_embeddings에 저장 (content=원문 JSON, embedding=요약문 임베딩)"
    )
    parser.add_argument("--input", "-i", type=Path, required=True, help="전사 JSON 파일 경로 (1.aac.raw.json 형태)")
    parser.add_argument("--course-id", required=True, help="course_id")
    parser.add_argument("--lecture-id", required=True, help="lecture_id")
    parser.add_argument("--user-id", required=True, help="user_id")
    parser.add_argument("--summary", "-s", default=None, help="요약문 (비우면 전사에서 LLM으로 자동 생성)")
    parser.add_argument("--course-title", default=None, help="강좌 제목 (대주제, 요약 프롬프트에 포함)")
    parser.add_argument("--section-title", default=None, help="섹션 제목 (소주제)")
    parser.add_argument("--lecture-title", default=None, help="강의 제목 (소주제)")
    args = parser.parse_args()

    path = args.input
    if not path.exists():
        print(f"파일 없음: {path}", file=sys.stderr)
        sys.exit(1)

    logger.info("전사 파일 로드 중 path=%s", path)
    with open(path, encoding="utf-8") as f:
        content_json = json.load(f)

    lecture_store_service.store(
        course_id=args.course_id,
        lecture_id=args.lecture_id,
        user_id=args.user_id,
        content_json=content_json,
        summary=args.summary.strip() if args.summary else None,
        course_title=args.course_title,
        section_title=args.section_title,
        lecture_title=args.lecture_title,
    )
    logger.info("저장 완료 course_id=%s lecture_id=%s user_id=%s", args.course_id, args.lecture_id, args.user_id)
    print(f"저장 완료: course_id={args.course_id}, lecture_id={args.lecture_id}, user_id={args.user_id}")


if __name__ == "__main__":
    main()
