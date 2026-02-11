"""
SQLModel 엔진·세션 (PostgreSQL + pgvector).
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.db.models import (  # noqa: F401 - 테이블 등록
    IngestionJob,
    LectureChunk,
    LectureChunkVector,
    LectureQuiz,
    LectureSummaryEmbedding,
)

# postgresql:// → postgresql+psycopg:// (psycopg3 드라이버)
_db_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(_db_url, echo=False)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    # pgvector 확장 없으면 생성 후 테이블 생성 (DB 연결은 여기서 발생)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE lecture_summary_embeddings ADD COLUMN IF NOT EXISTS summary TEXT"))
        conn.execute(text("ALTER TABLE lecture_quiz ADD COLUMN IF NOT EXISTS approved BOOLEAN NOT NULL DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE lecture_quiz ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ"))
        conn.commit()
    with Session(engine) as session:
        yield session
