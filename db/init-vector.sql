-- pgvector 확장 활성화
CREATE EXTENSION IF NOT EXISTS vector;

-- 임베딩 저장용 테이블 (전사 청크, 퀴즈 등 벡터 검색용)
-- 나중에 앱에서 이 테이블에 넣고 유사도 검색 가능
CREATE TABLE IF NOT EXISTS lecture_summary_embeddings (
    id         BIGSERIAL PRIMARY KEY,
    course_id  TEXT NOT NULL,
    lecture_id TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    content    JSONB NOT NULL,          -- 원문 (JSON: 전사 segments 등)
    embedding  vector(1536),            -- OpenAI text-embedding-3-small 기본 차원
    metadata   JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (course_id, lecture_id, user_id)
);

-- 유사도 검색용 인덱스 (cosine distance)
CREATE INDEX IF NOT EXISTS idx_lecture_summary_embeddings
ON lecture_summary_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

COMMENT ON TABLE lecture_summary_embeddings IS '강의 요약 벡터 검색용 문서/전사 청크 임베딩';

-- 퀴즈 저장 (문항 목록 JSON: question, options(배열), answer, explanation 등 그대로)
CREATE TABLE IF NOT EXISTS lecture_quiz (
    id          BIGSERIAL PRIMARY KEY,
    course_id   TEXT NOT NULL,
    lecture_id  TEXT NOT NULL,
    questions   JSONB NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    approved    BOOLEAN NOT NULL DEFAULT FALSE,
    approved_at TIMESTAMPTZ
);

COMMENT ON TABLE lecture_quiz IS '강의별 퀴즈 (문항별 question, options, answer, explanation 등 JSON 그대로)';
COMMENT ON COLUMN lecture_quiz.approved IS '승인 여부';
COMMENT ON COLUMN lecture_quiz.approved_at IS '승인 시점';

-- Ingestion pipeline: job queue
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id          BIGSERIAL PRIMARY KEY,
    course_id   TEXT NOT NULL,
    lecture_id  TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    job_type    TEXT NOT NULL,
    payload     JSONB NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ
);

-- SQL/Doc DB: chunks (concept, metadata, difficulty)
CREATE TABLE IF NOT EXISTS lecture_chunks (
    id          BIGSERIAL PRIMARY KEY,
    course_id   TEXT NOT NULL,
    lecture_id  TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    chunk_index INT NOT NULL,
    content     JSONB NOT NULL,
    concept     TEXT,
    metadata    JSONB DEFAULT '{}',
    difficulty  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Vector Store: chunk embeddings only
CREATE TABLE IF NOT EXISTS lecture_chunk_vectors (
    id          BIGSERIAL PRIMARY KEY,
    chunk_id    BIGINT NOT NULL,
    embedding   vector(1536) NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_lecture_chunk_vectors_embedding
ON lecture_chunk_vectors USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
