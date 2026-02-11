"""
lecture_chunks, lecture_chunk_vectors 테이블 접근 (SQL + Vector Store 분리).
"""

from typing import Any

from sqlmodel import select
from sqlmodel import Session

from app.db.models import LectureChunk, LectureChunkVector


class LectureChunkRepo:
    def insert(
        self,
        session: Session,
        *,
        course_id: str,
        lecture_id: str,
        user_id: str,
        chunk_index: int,
        content: dict[str, Any],
        concept: str | None = None,
        metadata_: dict[str, Any] | None = None,
        difficulty: str | None = None,
    ) -> LectureChunk:
        row = LectureChunk(
            course_id=course_id,
            lecture_id=lecture_id,
            user_id=user_id,
            chunk_index=chunk_index,
            content=content,
            concept=concept,
            metadata_=metadata_ or {},
            difficulty=difficulty,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row

    def insert_vector(self, session: Session, chunk_id: int, embedding: list[float]) -> None:
        row = LectureChunkVector(chunk_id=chunk_id, embedding=embedding)
        session.add(row)
        session.commit()

    def delete_by_lecture(
        self, session: Session, course_id: str, lecture_id: str, user_id: str
    ) -> None:
        chunks = list(
            session.exec(
                select(LectureChunk).where(
                    LectureChunk.course_id == course_id,
                    LectureChunk.lecture_id == lecture_id,
                    LectureChunk.user_id == user_id,
                )
            ).all()
        )
        for c in chunks:
            if c.id is not None:
                for v in session.exec(
                    select(LectureChunkVector).where(LectureChunkVector.chunk_id == c.id)
                ).all():
                    session.delete(v)
            session.delete(c)
        session.commit()


lecture_chunk_repo = LectureChunkRepo()
