"""
전사 JSON + 요약문 임베딩을 DB에 저장하는 오케스트레이션.
"""

import logging
from typing import Any

from app.db.connection import get_session

logger = logging.getLogger(__name__)
from app.db.repositories.lecture_summary_embeddings import (
    LectureSummaryEmbeddingRow,
    lecture_summary_embeddings_repo,
)
from app.services.embedding import embedding_service
from app.services.summary import summary_service


class LectureStoreService:
    """강의 전사(content) + 요약 임베딩을 lecture_summary_embeddings에 저장."""

    def store(
        self,
        course_id: str,
        lecture_id: str,
        user_id: str,
        content_json: dict[str, Any],
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
        *,
        course_title: str | None = None,
        section_title: str | None = None,
        lecture_title: str | None = None,
    ) -> str:
        """저장 후 사용된 요약문을 반환한다."""
        if summary is None or not summary.strip():
            logger.info("요약 없음 → LLM 요약 생성 중")
            summary = summary_service.summarize(
                content_json,
                course_title=course_title,
                section_title=section_title,
                lecture_title=lecture_title,
            )
            logger.info("요약 생성 완료 (길이=%d)", len(summary))
        summary = summary or ""
        logger.info("임베딩 생성 중")
        embedding = embedding_service.embed(summary)
        logger.info("DB 저장 중 (upsert)")
        row = LectureSummaryEmbeddingRow(
            course_id=course_id,
            lecture_id=lecture_id,
            user_id=user_id,
            content=content_json,
            summary=summary,
            embedding=embedding,
            metadata=metadata or {},
        )
        with get_session() as session:
            lecture_summary_embeddings_repo.upsert(session, row)
        return summary


lecture_store_service = LectureStoreService()
