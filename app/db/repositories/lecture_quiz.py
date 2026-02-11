"""
lecture_quiz 테이블 접근.
questions: JSON 배열, 각 문항은 question, options(리스트), answer, explanation 등 그대로 저장.
PostgreSQL JSONB는 options 같은 배열도 그대로 저장 가능.
"""

from typing import Any

from sqlmodel import Session

from app.db.models import LectureQuiz


class LectureQuizRepo:
    """퀴즈 저장."""

    def insert(
        self,
        session: Session,
        course_id: str,
        lecture_id: str,
        questions: list[dict[str, Any]],
    ) -> LectureQuiz:
        row = LectureQuiz(
            course_id=course_id,
            lecture_id=lecture_id,
            questions=questions,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


lecture_quiz_repo = LectureQuizRepo()
