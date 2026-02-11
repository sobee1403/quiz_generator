"""
API 요청/응답 스키마.
"""

from typing import Any

from pydantic import BaseModel, Field


# ----- 강의 요약·저장 -----


class LectureSummarizeRequest(BaseModel):
    """강의 전사 저장(요약 생성 후 DB 저장) 요청."""

    content: dict[str, Any] = Field(..., description="전사 JSON (segments 등)")
    course_id: str = Field(..., description="강좌 ID")
    lecture_id: str = Field(..., description="강의 ID")
    user_id: str = Field(..., description="사용자 ID")
    course_title: str | None = Field(None, description="강좌 제목 (대주제)")
    section_title: str | None = Field(None, description="섹션 제목 (소주제)")
    lecture_title: str | None = Field(None, description="강의 제목 (소주제)")
    summary: str | None = Field(None, description="미리 만든 요약문 (있으면 LLM 호출 생략)")


class LectureSummarizeResponse(BaseModel):
    """강의 요약·저장 응답."""

    summary: str = Field(..., description="저장된 요약문")
    message: str = Field(..., description="안내 메시지")


# ----- 퀴즈 생성 -----


class QuizGenerateRequest(BaseModel):
    """퀴즈 생성 요청."""

    course_id: str = Field(..., description="강좌 ID")
    lecture_id: str = Field(..., description="강의 ID")
    user_id: str = Field(..., description="사용자 ID")
    num_questions: int = Field(5, ge=1, le=20, description="문항 수")
    save: bool = Field(False, description="생성 결과를 lecture_quiz 테이블에 저장할지 여부")
    validate: bool = Field(True, description="문항별 검증(LLM 정답 일치) 수행 여부")
    use_semantic_previous: bool = Field(False, description="이전 맥락을 id 순 전부 대신 벡터 유사도 상위 N건만 사용")
    semantic_limit: int = Field(5, ge=1, le=20, description="use_semantic_previous 시 참고할 이전 강의 요약 최대 건수")
    max_context_lectures: int | None = Field(None, ge=1, le=100, description="맥락에 쓸 이전 강의를 id 순 처음 N개로 제한. 예: 5면 1~5번만, 6번 이후 미반영")


class QuizQuestionOption(BaseModel):
    """퀴즈 문항 한 개 (API 응답용)."""

    question: str
    options: list[str]
    answer: int
    explanation: str
    verified: bool | None = None  # validate=True일 때만 존재


class QuizGenerateResponse(BaseModel):
    """퀴즈 생성 응답."""

    questions: list[QuizQuestionOption] = Field(..., description="퀴즈 문항 목록")
    saved: bool = Field(False, description="DB(lecture_quiz)에 저장했는지 여부")


# ----- Ingestion (Upload → Queue) -----


class LectureUploadResponse(BaseModel):
    """업로드 시 큐 적재 응답."""

    job_id: int = Field(..., description="ingestion job ID")
    message: str = Field(..., description="안내 메시지")


class IngestionJobStatusResponse(BaseModel):
    """Ingestion job 상태 조회 응답."""

    job_id: int
    status: str = Field(..., description="pending | processing | done | failed")
    error_message: str | None = None


class IngestionEnqueueRequest(BaseModel):
    """전사 JSON으로 ingestion job 적재 요청."""

    course_id: str
    lecture_id: str
    user_id: str
    transcript: dict[str, Any] | None = None
    content: dict[str, Any] | None = None  # transcript 대용
    concept_hint: str | None = Field(None, description="강사가 달아준 강의 제목/개념. 검증 후 사용, 나쁘면 LLM이 보완.")
    lecture_title: str | None = Field(None, description="concept_hint와 동일하게 사용되는 강의 제목")
