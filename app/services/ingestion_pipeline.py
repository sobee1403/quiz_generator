"""
Ingestion 파이프라인: STT(선택) → Span Chunking → 병렬 Concept/Metadata/Difficulty → Vector Store + SQL 저장.
"""

import logging
from pathlib import Path
from typing import Any

from app.db.connection import get_session
from app.db.repositories.ingestion_job import ingestion_job_repo
from app.db.repositories.lecture_chunk import lecture_chunk_repo
from app.services.chunking import chunk_by_max_chars
from app.services.embedding import embedding_service
from app.services.extractors import extract_parallel
from app.services.stt import transcribe

logger = logging.getLogger(__name__)


def run_pipeline(job_id: int) -> None:
    """
    단일 ingestion job 실행: payload에 따라 STT 후 청킹 → 병렬 추출 → SQL + Vector 저장.
    """
    with get_session() as session:
        job = ingestion_job_repo.get_by_id(session, job_id)
        if not job or job.status != "pending":
            return
        ingestion_job_repo.mark_processing(session, job_id)
        payload = dict(job.payload)
        course_id = job.course_id
        lecture_id = job.lecture_id
        user_id = job.user_id
        job_type = job.job_type

    try:

        if job_type == "audio":
            audio_path = payload.get("audio_path")
            if not audio_path:
                raise ValueError("audio job requires payload.audio_path")
            path = Path(audio_path)
            if not path.exists():
                raise FileNotFoundError(f"Audio file not found: {path}")
            logger.info("STT 실행 중 path=%s", path)
            content_json = transcribe(path)
        else:
            content_json = payload.get("transcript") or payload.get("content") or payload
            if not isinstance(content_json, dict) or "segments" not in content_json:
                raise ValueError("transcript job requires payload.transcript with segments")

        segments = content_json.get("segments") or []
        chunks = chunk_by_max_chars(segments, max_chars=1500)
        logger.info("Span chunking 완료 청크 수=%d", len(chunks))

        with get_session() as session:
            lecture_chunk_repo.delete_by_lecture(session, course_id, lecture_id, user_id)

        concept_hint = (payload.get("concept_hint") or payload.get("lecture_title") or payload.get("concept") or "").strip() or None
        if concept_hint:
            logger.info("강사 제목(concept_hint) 사용·검증: %s", concept_hint[:50])

        for idx, ch in enumerate(chunks):
            text = ch.get("text") or ""
            if not text.strip():
                continue
            concept, metadata, difficulty = extract_parallel(text, concept_hint=concept_hint)
            embedding = embedding_service.embed(text)
            with get_session() as session:
                row = lecture_chunk_repo.insert(
                    session,
                    course_id=course_id,
                    lecture_id=lecture_id,
                    user_id=user_id,
                    chunk_index=idx,
                    content={"text": text, "start": ch.get("start"), "end": ch.get("end"), "segment_indices": ch.get("segment_indices", [])},
                    concept=concept or None,
                    metadata_=metadata,
                    difficulty=difficulty,
                )
                if row.id is not None:
                    lecture_chunk_repo.insert_vector(session, row.id, embedding)

        with get_session() as session:
            ingestion_job_repo.mark_done(session, job_id)
        logger.info("Ingestion 완료 job_id=%s", job_id)
    except Exception as e:
        logger.exception("Ingestion 실패 job_id=%s", job_id)
        with get_session() as session:
            ingestion_job_repo.mark_failed(session, job_id, str(e))
        raise
