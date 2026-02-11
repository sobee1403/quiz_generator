"""
FastAPI 앱: 강의 요약·저장, 퀴즈 생성, 업로드→Ingestion 큐 API.
"""

import logging
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import File, HTTPException, UploadFile

from app.api.schemas import (
    IngestionJobStatusResponse,
    IngestionEnqueueRequest,
    LectureSummarizeRequest,
    LectureSummarizeResponse,
    LectureUploadResponse,
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizQuestionOption,
)
from app.db.connection import get_session
from app.db.repositories.ingestion_job import ingestion_job_repo
from app.services.lecture_store import lecture_store_service
from app.services.quiz_from_lecture import quiz_from_lecture_service

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", tempfile.gettempdir())) / "quiz_generator_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# FastAPI app은 router를 쓰지 않고 여기서 직접 등록 (또는 라우터 분리 가능)
def create_app():
    from fastapi import FastAPI, Form
    app = FastAPI(
        title="Quiz Generator API",
        description="강의 전사 요약·저장, 요약 기준 퀴즈 생성, 업로드→Ingestion 큐",
        version="0.1.0",
    )

    @app.post(
        "/lectures/upload",
        response_model=LectureUploadResponse,
        summary="강의 업로드 (Ingestion Job Enqueue)",
        description="음성 파일 업로드 시 큐에 적재. Worker가 STT → Chunking → Concept/Metadata/Difficulty → Vector+SQL 저장.",
    )
    async def lecture_upload(
        course_id: str = Form(...),
        lecture_id: str = Form(...),
        user_id: str = Form(...),
        file: UploadFile = File(...),
        concept_hint: str | None = Form(None),
        lecture_title: str | None = Form(None),
    ) -> LectureUploadResponse:
        try:
            suffix = Path(file.filename or "bin").suffix or ".bin"
            path = UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
            content = await file.read()
            path.write_bytes(content)
            payload = {"audio_path": str(path)}
            if concept_hint and concept_hint.strip():
                payload["concept_hint"] = concept_hint.strip()
            if lecture_title and lecture_title.strip():
                payload["lecture_title"] = lecture_title.strip()
            with get_session() as session:
                job = ingestion_job_repo.create(
                    session,
                    course_id=course_id,
                    lecture_id=lecture_id,
                    user_id=user_id,
                    job_type="audio",
                    payload=payload,
                )
            return LectureUploadResponse(
                job_id=job.id if job.id else 0,
                message="Ingestion job enqueued. Run worker to process.",
            )
        except Exception as e:
            logger.exception("업로드 실패")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post(
        "/lectures/ingestion/enqueue",
        response_model=LectureUploadResponse,
        summary="전사 JSON으로 Ingestion Job Enqueue",
    )
    def ingestion_enqueue(body: IngestionEnqueueRequest) -> LectureUploadResponse:
        try:
            transcript = body.transcript or body.content
            if not transcript:
                raise HTTPException(status_code=400, detail="transcript or content required")
            payload = {"transcript": transcript}
            if body.concept_hint and body.concept_hint.strip():
                payload["concept_hint"] = body.concept_hint.strip()
            if body.lecture_title and body.lecture_title.strip():
                payload["lecture_title"] = body.lecture_title.strip()
            with get_session() as session:
                job = ingestion_job_repo.create(
                    session,
                    course_id=body.course_id,
                    lecture_id=body.lecture_id,
                    user_id=body.user_id,
                    job_type="transcript",
                    payload=payload,
                )
            return LectureUploadResponse(
                job_id=job.id if job.id else 0,
                message="Ingestion job enqueued.",
            )
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception("Enqueue 실패")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get(
        "/lectures/ingestion/jobs/{job_id:int}",
        response_model=IngestionJobStatusResponse,
        summary="Ingestion job 상태 조회",
    )
    def ingestion_job_status(job_id: int) -> IngestionJobStatusResponse:
        with get_session() as session:
            job = ingestion_job_repo.get_by_id(session, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return IngestionJobStatusResponse(
            job_id=job_id,
            status=job.status,
            error_message=job.error_message,
        )

    @app.post(
        "/lectures/summarize-and-store",
        response_model=LectureSummarizeResponse,
        summary="강의 요약 및 저장",
        description="전사 JSON을 받아 요약 생성(또는 전달된 요약 사용) 후 lecture_summary_embeddings에 저장. course_title/section_title/lecture_title은 요약 LLM 프롬프트(user)에 포함.",
    )
    def lecture_summarize_and_store(body: LectureSummarizeRequest) -> LectureSummarizeResponse:
        try:
            summary = lecture_store_service.store(
                course_id=body.course_id,
                lecture_id=body.lecture_id,
                user_id=body.user_id,
                content_json=body.content,
                summary=body.summary.strip() if body.summary else None,
                course_title=body.course_title,
                section_title=body.section_title,
                lecture_title=body.lecture_title,
            )
            return LectureSummarizeResponse(
                summary=summary,
                message="저장 완료",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception("강의 요약·저장 실패")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post(
        "/quiz/generate",
        response_model=QuizGenerateResponse,
        summary="퀴즈 생성",
        description="해당 강의 요약 기준으로 퀴즈 생성. 선택 시 검증(verified) 및 lecture_quiz 저장.",
    )
    def quiz_generate(body: QuizGenerateRequest) -> QuizGenerateResponse:
        try:
            if body.validate:
                result = quiz_from_lecture_service.generate_validated(
                    course_id=body.course_id,
                    lecture_id=body.lecture_id,
                    user_id=body.user_id,
                    num_questions=body.num_questions,
                    use_semantic_previous=body.use_semantic_previous,
                    semantic_limit=body.semantic_limit,
                    max_context_lectures=body.max_context_lectures,
                )
                questions_out = [
                    QuizQuestionOption(
                        question=q.question,
                        options=q.options,
                        answer=q.answer,
                        explanation=q.explanation,
                        verified=q.verified,
                    )
                    for q in result.questions
                ]
            else:
                result = quiz_from_lecture_service.generate(
                    course_id=body.course_id,
                    lecture_id=body.lecture_id,
                    user_id=body.user_id,
                    num_questions=body.num_questions,
                    use_semantic_previous=body.use_semantic_previous,
                    semantic_limit=body.semantic_limit,
                    max_context_lectures=body.max_context_lectures,
                )
                questions_out = [
                    QuizQuestionOption(
                        question=q.question,
                        options=q.options,
                        answer=q.answer,
                        explanation=q.explanation,
                        verified=None,
                    )
                    for q in result.questions
                ]
            saved = False
            if body.save:
                quiz_from_lecture_service.save_result(
                    course_id=body.course_id,
                    lecture_id=body.lecture_id,
                    result=result,
                )
                saved = True
            return QuizGenerateResponse(questions=questions_out, saved=saved)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception("퀴즈 생성 실패")
            raise HTTPException(status_code=500, detail=str(e))

    return app


app = create_app()
