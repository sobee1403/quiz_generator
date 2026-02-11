"""
SQLModel 테이블 정의 (pgvector 포함).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
from sqlmodel import Field, SQLModel


class IngestionJob(SQLModel, table=True):
    """업로드 이벤트 후 큐에 적재되는 ingestion 작업."""

    __tablename__ = "ingestion_jobs"

    id: int | None = Field(default=None, primary_key=True)
    course_id: str = Field(nullable=False)
    lecture_id: str = Field(nullable=False)
    user_id: str = Field(nullable=False)
    job_type: str = Field(nullable=False)  # "audio" | "transcript"
    payload: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))  # audio_path or content
    status: str = Field(default="pending", nullable=False)  # pending | processing | done | failed
    error_message: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
    updated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), onupdate=func.now()),
    )


class LectureChunk(SQLModel, table=True):
    """SQL/Doc DB: 청크별 concept, metadata, difficulty 등 (벡터 제외)."""

    __tablename__ = "lecture_chunks"

    id: int | None = Field(default=None, primary_key=True)
    course_id: str = Field(nullable=False)
    lecture_id: str = Field(nullable=False)
    user_id: str = Field(nullable=False)
    chunk_index: int = Field(nullable=False)
    content: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))  # text, start, end, segment_indices
    concept: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSONB, server_default="{}"),
    )
    difficulty: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )


class LectureChunkVector(SQLModel, table=True):
    """Vector Store: 청크 임베딩만 (유사도 검색용)."""

    __tablename__ = "lecture_chunk_vectors"

    id: int | None = Field(default=None, primary_key=True)
    chunk_id: int = Field(nullable=False)  # FK to lecture_chunks.id
    embedding: list[float] = Field(sa_column=Column(Vector(1536), nullable=False))
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )


class LectureSummaryEmbedding(SQLModel, table=True):
    """강의 요약 임베딩: content=원문 JSON, embedding=요약문 벡터."""

    __tablename__ = "lecture_summary_embeddings"
    __table_args__ = (UniqueConstraint("course_id", "lecture_id", "user_id"),)

    id: int | None = Field(default=None, primary_key=True)
    course_id: str = Field(nullable=False)
    lecture_id: str = Field(nullable=False)
    user_id: str = Field(nullable=False)
    content: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    summary: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    embedding: list[float] | None = Field(default=None, sa_column=Column(Vector(1536)))
    metadata_: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSONB, server_default="{}"),
    )
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )


class LectureQuiz(SQLModel, table=True):
    """강의별 퀴즈 저장. questions는 문항 배열(각 항목: question, options, answer, explanation 등 JSON 그대로)."""

    __tablename__ = "lecture_quiz"

    id: int | None = Field(default=None, primary_key=True)
    course_id: str = Field(nullable=False)
    lecture_id: str = Field(nullable=False)
    questions: list[dict[str, Any]] = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
    approved: bool = Field(default=False)
    approved_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
