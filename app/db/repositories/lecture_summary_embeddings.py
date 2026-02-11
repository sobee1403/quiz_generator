"""
lecture_summary_embeddings 테이블 접근 (SQLModel).

벡터 검색: 검색은 DB(pgvector)에서 수행되며, OpenAI는 쿼리 1개 벡터화할 때만 1회 호출.
자세한 설명 및 사용 예: docs/VECTOR_SEARCH.md
"""

from typing import Any

from sqlalchemy import text
from sqlmodel import select
from sqlmodel import Session

from app.db.models import LectureSummaryEmbedding


class LectureSummaryEmbeddingRow:
    """저장용 DTO (서비스 레이어 ↔ repository)."""

    def __init__(
        self,
        *,
        course_id: str,
        lecture_id: str,
        user_id: str,
        content: dict[str, Any],
        summary: str | None,
        embedding: list[float],
        metadata: dict[str, Any] | None = None,
    ):
        self.course_id = course_id
        self.lecture_id = lecture_id
        self.user_id = user_id
        self.content = content
        self.summary = summary
        self.embedding = embedding
        self.metadata = metadata or {}


class LectureSummaryEmbeddingsRepo:
    """강의 요약 임베딩 저장/조회 (SQLModel Session)."""

    def upsert(self, session: Session, row: LectureSummaryEmbeddingRow) -> None:
        stmt = select(LectureSummaryEmbedding).where(
            LectureSummaryEmbedding.course_id == row.course_id,
            LectureSummaryEmbedding.lecture_id == row.lecture_id,
            LectureSummaryEmbedding.user_id == row.user_id,
        )
        existing = session.exec(stmt).first()
        if existing:
            existing.content = row.content
            existing.summary = row.summary
            existing.embedding = row.embedding
            existing.metadata_ = row.metadata
            session.add(existing)
        else:
            session.add(
                LectureSummaryEmbedding(
                    course_id=row.course_id,
                    lecture_id=row.lecture_id,
                    user_id=row.user_id,
                    content=row.content,
                    summary=row.summary,
                    embedding=row.embedding,
                    metadata_=row.metadata,
                )
            )
        session.commit()

    def get_lecture(
        self, session: Session, course_id: str, lecture_id: str, user_id: str
    ) -> LectureSummaryEmbedding | None:
        stmt = select(LectureSummaryEmbedding).where(
            LectureSummaryEmbedding.course_id == course_id,
            LectureSummaryEmbedding.lecture_id == lecture_id,
            LectureSummaryEmbedding.user_id == user_id,
        )
        return session.exec(stmt).first()

    def get_previous_summaries(
        self, session: Session, course_id: str, user_id: str, before_id: int
    ) -> list[str]:
        """같은 강좌·유저에서 id < before_id 인 강의들의 summary 텍스트 목록 (id 오름차순)."""
        stmt = (
            select(LectureSummaryEmbedding.summary)
            .where(
                LectureSummaryEmbedding.course_id == course_id,
                LectureSummaryEmbedding.user_id == user_id,
                LectureSummaryEmbedding.id < before_id,
                LectureSummaryEmbedding.summary.is_not(None),
            )
            .order_by(LectureSummaryEmbedding.id.asc())
        )
        rows = session.exec(stmt).all()
        return [s for s in rows if s and s.strip()]

    def get_summaries_from_first_n_lectures(
        self,
        session: Session,
        course_id: str,
        user_id: str,
        first_n: int = 5,
        before_id: int | None = None,
    ) -> list[str]:
        """
        같은 강좌·유저에서 id 순 처음 first_n 개 강의에 해당하는 요약만 반환.
        before_id 를 주면 그보다 id 가 작은 행만 포함(현재 강의 및 그 이후 제외).
        예: 30개 강의 중 5번까지만 맥락에 쓰고 6번 이후는 반영하지 않을 때 first_n=5, before_id=현재강의id.
        """
        subq = (
            select(LectureSummaryEmbedding.id)
            .where(
                LectureSummaryEmbedding.course_id == course_id,
                LectureSummaryEmbedding.user_id == user_id,
            )
            .order_by(LectureSummaryEmbedding.id.asc())
            .limit(first_n)
        )
        conditions = [
            LectureSummaryEmbedding.course_id == course_id,
            LectureSummaryEmbedding.user_id == user_id,
            LectureSummaryEmbedding.summary.is_not(None),
            LectureSummaryEmbedding.id.in_(subq),
        ]
        if before_id is not None:
            conditions.append(LectureSummaryEmbedding.id < before_id)
        stmt = (
            select(LectureSummaryEmbedding.summary)
            .where(*conditions)
            .order_by(LectureSummaryEmbedding.id.asc())
        )
        rows = session.exec(stmt).all()
        return [s for s in rows if s and s.strip()]

    def get_similar_summaries(
        self,
        session: Session,
        course_id: str,
        user_id: str,
        query_embedding: list[float],
        limit: int = 5,
        exclude_lecture_id: str | None = None,
    ) -> list[tuple[str, str]]:
        """
        같은 강좌·유저 내에서 쿼리 벡터와 코사인 유사도가 높은 순으로 강의 요약 조회.
        검색은 전부 DB(pgvector)에서 수행되며, query_embedding은 이미 EmbeddingService 등으로 만든 벡터.

        Returns:
            (lecture_id, summary) 리스트. summary가 None이면 제외.
        """
        # pgvector에 넘길 때 '[0.1,0.2,...]' 형태 문자열
        vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        exclude = exclude_lecture_id or ""
        sql = text("""
            SELECT lecture_id, summary
            FROM lecture_summary_embeddings
            WHERE course_id = :course_id
              AND user_id = :user_id
              AND embedding IS NOT NULL
              AND summary IS NOT NULL
              AND (:exclude = '' OR lecture_id != :exclude)
            ORDER BY embedding <=> :query_embedding::vector
            LIMIT :limit
        """)
        rows = session.execute(
            sql,
            {
                "course_id": course_id,
                "user_id": user_id,
                "query_embedding": vec_str,
                "exclude": exclude,
                "limit": limit,
            },
        ).fetchall()
        return [(r[0], r[1]) for r in rows if r[1] and r[1].strip()]


lecture_summary_embeddings_repo = LectureSummaryEmbeddingsRepo()
