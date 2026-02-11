"""
acc 전사 파일을 차례대로 store_lecture → 퀴즈 생성하는 파이프라인 테스트.

- DB + OpenAI 필요. acc/transcripts/gpt-4o-transcribe-diarize/*.aac.raw.json 없으면 skip.
- 실행: quiz_generator 디렉터리에서
    pytest tests/ -v
    pytest tests/test_lecture_pipeline.py -v
"""

import json
import logging

import pytest

from app.services.lecture_store import lecture_store_service
from app.services.quiz_from_lecture import quiz_from_lecture_service

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def test_store_lectures_from_acc_in_order(acc_raw_entries, test_course_id, test_user_id):
    """acc 전사 1~5를 차례대로 store_lecture (요약 자동 생성)."""
    for n, path in acc_raw_entries:
        with open(path, encoding="utf-8") as f:
            content_json = json.load(f)
        lecture_id = f"lecture_{n}"
        lecture_store_service.store(
            course_id=test_course_id,
            lecture_id=lecture_id,
            user_id=test_user_id,
            content_json=content_json,
            summary=None,
        )
        logger.info("저장 완료 lecture_id=%s", lecture_id)


def test_quiz_generation_for_each_lecture(acc_raw_entries, test_course_id, test_user_id):
    """각 강의(lecture_1..N)에 대해 퀴즈 생성 및 검증, 스키마 검사. (store 후 실행 권장)"""
    for n, _path in acc_raw_entries:
        lecture_id = f"lecture_{n}"
        result = quiz_from_lecture_service.generate_validated(
            course_id=test_course_id,
            lecture_id=lecture_id,
            user_id=test_user_id,
            num_questions=2,
        )
        assert len(result.questions) >= 1, f"lecture_{n} 퀴즈 문항 없음"
        for i, q in enumerate(result.questions):
            assert q.question, f"lecture_{n} 문항 {i} question 비어 있음"
            assert len(q.options) == 5, f"lecture_{n} 문항 {i} options 5개 아님"
            assert 1 <= q.answer <= 5, f"lecture_{n} 문항 {i} answer 1~5 아님"
            assert q.explanation is not None, f"lecture_{n} 문항 {i} explanation 없음"
            assert isinstance(q.verified, bool), f"lecture_{n} 문항 {i} verified 없음"
        logger.info(
            "lecture_id=%s 문항 수=%d 검증 통과=%d",
            lecture_id,
            len(result.questions),
            sum(1 for q in result.questions if q.verified),
        )
