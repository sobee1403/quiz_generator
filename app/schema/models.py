"""
요청/응답 스키마 정의.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

QuestionType = Literal["multiple_choice", "true_false", "short_answer"]
Difficulty = Literal["easy", "medium", "hard"]


class Segment(BaseModel):
    text: str = Field(min_length=1)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    speaker: str | None = None

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def validate_time_range(self):
        if self.end < self.start:
            raise ValueError("segment.end must be >= segment.start")
        return self


class TranscriptMeta(BaseModel):
    model: str | None = None
    audio_id: str | None = None
    created_at: str | None = None
    duration: float | None = None
    language_hint: str | None = None


class TranscriptData(BaseModel):
    meta: TranscriptMeta | None = None
    segments: list[Segment]


class QuizRequest(BaseModel):
    segments: list[Segment]
    meta: TranscriptMeta | None = None
    num_questions: int = Field(default=5, ge=1, le=30)
    question_types: list[QuestionType] = Field(default_factory=lambda: ["multiple_choice"])
    language: str = Field(default="ko", min_length=2, max_length=8)
    difficulty: Difficulty = "medium"


class QuizQuestion(BaseModel):
    id: str
    type: QuestionType
    question: str
    options: list[str] | None = None
    answer: str
    explanation: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)


class QuizDraft(BaseModel):
    title: str
    language: str
    questions: list[QuizQuestion]


class QuizSource(BaseModel):
    segment_count: int
    start: float
    end: float
    truncated: bool = False


class QuizResponse(QuizDraft):
    source: QuizSource
