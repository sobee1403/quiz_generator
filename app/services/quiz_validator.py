"""
퀴즈 문항 검증: 질문 + 보기 5개를 주고, LLM이 정답 번호(1~5)를 고르게 한 뒤
생성 시 주어진 정답과 일치하면 검증 통과(verified=True).
"""

import logging
import re

from openai import OpenAI

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.schema.quiz_lecture import (
    QuizFromLectureResponse,
    QuizQuestionItem,
    ValidatedQuizQuestionItem,
    ValidatedQuizFromLectureResponse,
)


class QuizValidatorService:
    """질문과 보기만 주고 정답을 골라서, 원 정답과 일치 여부로 검증."""

    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.REQUEST_TIMEOUT,
        )

    def pick_answer(self, question: str, options: list[str]) -> int | None:
        """
        질문과 보기 5개를 주고, LLM이 정답인 보기 번호(1~5)를 고르게 한다.
        반환: 1~5 또는 파싱 실패 시 None.
        """
        opts_text = "\n".join(f"{i}. {opt}" for i, opt in enumerate(options, 1))
        system_prompt = (
            "너는 퀴즈 채점자다. 질문과 5개 보기를 보고 정답인 보기 번호(1, 2, 3, 4, 5 중 하나)만 판단한다. "
            "답은 반드시 숫자 하나만 출력한다. 예: 3"
        )
        user_prompt = f"질문: {question}\n\n보기:\n{opts_text}\n\n정답 번호(1~5):"

        response = self._client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=0.0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        match = re.search(r"[1-5]", raw)
        if match:
            return int(match.group())
        logger.warning("검증기 정답 파싱 실패 raw=%r", raw)
        return None

    def validate_one(self, item: QuizQuestionItem) -> ValidatedQuizQuestionItem:
        """한 문항 검증: LLM이 고른 정답이 item.answer와 같으면 verified=True."""
        picked = self.pick_answer(item.question, item.options)
        verified = picked is not None and picked == item.answer
        logger.info(
            "문항 검증 LLM선택=%s 정답=%s verified=%s",
            picked,
            item.answer,
            verified,
        )
        if not verified:
            logger.warning(
                "verified=false → 검증기(LLM)가 고른 정답=%s, 출제 정답=%s",
                picked,
                item.answer,
            )
        return ValidatedQuizQuestionItem(
            question=item.question,
            options=item.options,
            answer=item.answer,
            explanation=item.explanation,
            verified=verified,
        )

    def validate_all(self, response: QuizFromLectureResponse) -> ValidatedQuizFromLectureResponse:
        """전체 퀴즈 응답을 받아 문항별로 검증한 뒤 ValidatedQuizFromLectureResponse 반환."""
        validated = []
        for i, q in enumerate(response.questions, 1):
            logger.info("검증 중 (%d/%d)", i, len(response.questions))
            validated.append(self.validate_one(q))
        return ValidatedQuizFromLectureResponse(questions=validated)


quiz_validator_service = QuizValidatorService()