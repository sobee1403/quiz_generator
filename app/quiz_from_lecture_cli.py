"""
요약 기준 퀴즈 생성 CLI. 기본으로 생성 후 검증(질문+보기로 LLM 정답 분류, 일치 시 verified=True).

사용 예:
  python -m app.quiz_from_lecture_cli --course-id course1 --lecture-id lecture1 --user-id user1
  python -m app.quiz_from_lecture_cli --course-id c1 --lecture-id l1 --user-id u1 --num-questions 5 --pretty
  python -m app.quiz_from_lecture_cli ... --no-validate  # 검증 단계 생략
로그는 stderr, JSON 결과는 stdout으로 출력된다.
"""

import argparse
import json
import logging
import sys

from app.services.quiz_from_lecture import quiz_from_lecture_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="해당 강의 요약 기준 퀴즈 생성 (이전 요약 참고, 이후 강의 미포함). 기본으로 검증 단계 포함."
    )
    parser.add_argument("--course-id", required=True, help="course_id")
    parser.add_argument("--lecture-id", required=True, help="lecture_id")
    parser.add_argument("--user-id", required=True, help="user_id")
    parser.add_argument("--num-questions", "-n", type=int, default=5, help="문항 수 (기본 5)")
    parser.add_argument("--no-validate", action="store_true", help="검증 단계 생략 (verified 없이 반환)")
    parser.add_argument("--save", action="store_true", help="생성한 퀴즈 결과를 DB(lecture_quiz)에 저장")
    parser.add_argument("--semantic-previous", action="store_true", help="이전 강의 맥락을 id 순 대신 벡터 유사도 상위 N건만 사용 (docs/VECTOR_SEARCH.md 참고)")
    parser.add_argument("--semantic-limit", type=int, default=5, help="--semantic-previous 사용 시 참고할 이전 강의 요약 최대 건수 (기본 5)")
    parser.add_argument("--max-context-lectures", type=int, default=None, metavar="N", help="맥락에 쓸 이전 강의를 id 순 처음 N개로 제한 (예: 5 → 1~5번만, 6번 이후 미반영)")
    parser.add_argument("--pretty", action="store_true", help="JSON 예쁘게 출력")
    args = parser.parse_args()

    logger.info(
        "퀴즈 생성 시작 course_id=%s lecture_id=%s user_id=%s num_questions=%s validate=%s semantic_previous=%s",
        args.course_id,
        args.lecture_id,
        args.user_id,
        args.num_questions,
        not args.no_validate,
        args.semantic_previous,
    )
    try:
        gen_kw = dict(
            course_id=args.course_id,
            lecture_id=args.lecture_id,
            user_id=args.user_id,
            num_questions=args.num_questions,
            use_semantic_previous=args.semantic_previous,
            semantic_limit=args.semantic_limit,
            max_context_lectures=args.max_context_lectures,
        )
        if args.no_validate:
            result = quiz_from_lecture_service.generate(**gen_kw)
            logger.info("퀴즈 생성 완료 (검증 없음) 문항 수=%d", len(result.questions))
        else:
            result = quiz_from_lecture_service.generate_validated(**gen_kw)
            verified_count = sum(1 for q in result.questions if q.verified)
            logger.info(
                "퀴즈 생성 및 검증 완료 문항 수=%d 검증 통과=%d",
                len(result.questions),
                verified_count,
            )
        if args.save:
            quiz_from_lecture_service.save_result(
                course_id=args.course_id,
                lecture_id=args.lecture_id,
                result=result,
            )
    except ValueError as e:
        logger.exception("오류 발생")
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)

    out = result.model_dump()
    if args.pretty:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
