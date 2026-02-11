"""
요약 기준 퀴즈 생성 요청/응답 스키마.
- 질문, 선택지 5개, 정답(1~5), 해설.
"""

from pydantic import BaseModel, Field, field_validator


class QuizQuestionItem(BaseModel):
    """퀴즈 한 문항: 질문, 5개 선택지, 정답 번호(1~5), 해설."""

    question: str = Field(..., min_length=1, description="질문 문장")
    options: list[str] = Field(..., min_length=5, max_length=5, description="선택지 1~5번")
    answer: int = Field(..., ge=1, le=5, description="정답 번호 (1~5)")
    explanation: str = Field(..., description="해설")

    @field_validator("options")
    @classmethod
    def options_five(cls, v: list[str]) -> list[str]:
        if len(v) != 5:
            raise ValueError("선택지는 정확히 5개여야 합니다")
        return [s.strip() for s in v]


class QuizFromLectureResponse(BaseModel):
    """요약 기준 퀴즈 생성 결과."""

    questions: list[QuizQuestionItem] = Field(..., description="퀴즈 문항 목록")


class ValidatedQuizQuestionItem(QuizQuestionItem):
    """검증까지 완료된 퀴즈 문항: 원 문항 + 검증 통과 여부."""

    verified: bool = Field(..., description="검증기(LLM)가 고른 정답이 원 정답과 일치하면 True")


class ValidatedQuizFromLectureResponse(BaseModel):
    """검증 단계를 거친 퀴즈 생성 결과."""

    questions: list[ValidatedQuizQuestionItem] = Field(..., description="문항 목록 (검증 여부 포함)")
