"""
전사 세그먼트를 기반으로 퀴즈 생성.
"""

from __future__ import annotations

from typing import Iterable

from openai import OpenAI

from app.core.config import settings
from app.schema.models import (
    QuizDraft,
    QuizQuestion,
    QuizRequest,
    QuizResponse,
    QuizSource,
)


def format_ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"
    return f"{minutes:02d}:{secs:05.2f}"


def format_segments(segments: Iterable, max_chars: int | None) -> tuple[str, bool]:
    lines: list[str] = []
    for idx, seg in enumerate(segments, 1):
        speaker = f"[{seg.speaker}]" if seg.speaker else ""
        line = f"{idx:04d} {format_ts(seg.start)}-{format_ts(seg.end)} {speaker} {seg.text}"
        lines.append(line.strip())
    transcript = "\n".join(lines)

    truncated = False
    if max_chars and len(transcript) > max_chars:
        transcript = transcript[:max_chars]
        truncated = True
    return transcript, truncated


def build_prompt(req: QuizRequest, transcript: str) -> tuple[str, str]:
    question_types = ", ".join(req.question_types)
    system_prompt = (
        "너는 한국어 강의 전사를 읽고 학습용 퀴즈를 만드는 전문가다. "
        "외부 지식에 의존하지 말고 제공된 전사 내용만 사용한다."
    )
    user_prompt = f"""
아래 전사를 기반으로 퀴즈를 만들어줘.

요청 조건:
- 질문 수: {req.num_questions}
- 질문 유형: {question_types}
- 난이도: {req.difficulty}
- 언어: {req.language}
- 질문은 전사 내용에만 근거해야 함
- 각 질문에는 근거가 되는 시간 구간(start/end)을 포함

출력은 JSON만 반환해. 다른 텍스트는 절대 포함하지 마.

JSON 형식:
{{
  "title": "string",
  "language": "{req.language}",
  "questions": [
    {{
      "id": "q1",
      "type": "multiple_choice | true_false | short_answer",
      "question": "string",
      "options": ["string", "string", "string", "string"] | null,
      "answer": "string",
      "explanation": "string",
      "start": 0.0,
      "end": 0.0
    }}
  ]
}}

규칙:
- multiple_choice: options는 4개 필수
- true_false, short_answer: options는 null로 설정

전사:
{transcript}
""".strip()
    return system_prompt, user_prompt


def build_repair_prompt(req: QuizRequest, bad_json: str, error: str) -> str:
    return f"""
다음 JSON이 스키마 검증에 실패했어. 에러 메시지를 참고해서 JSON만 수정해 줘.

에러:
{error}

원본 JSON:
{bad_json}

요청 조건:
- 질문 수: {req.num_questions}
- 질문 유형: {", ".join(req.question_types)}
- 난이도: {req.difficulty}
- 언어: {req.language}
- JSON만 출력
""".strip()


class QuizGenerator:
    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.REQUEST_TIMEOUT,
        )

    def generate(self, req: QuizRequest) -> QuizResponse:
        transcript, truncated = format_segments(req.segments, settings.MAX_TRANSCRIPT_CHARS)
        system_prompt, user_prompt = build_prompt(req, transcript)

        content = self._call_llm(system_prompt, user_prompt)
        try:
            draft = QuizDraft.model_validate_json(content)
        except Exception as exc:
            repair_prompt = build_repair_prompt(req, content, str(exc))
            content = self._call_llm(system_prompt, repair_prompt)
            draft = QuizDraft.model_validate_json(content)

        normalized_questions = self._normalize_questions(draft.questions, req)
        source = self._build_source(req, truncated)

        return QuizResponse(
            title=draft.title,
            language=draft.language,
            questions=normalized_questions,
            source=source,
        )

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=settings.OPENAI_TEMPERATURE,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or "{}"

    def _normalize_questions(self, questions: list[QuizQuestion], req: QuizRequest) -> list[QuizQuestion]:
        normalized: list[QuizQuestion] = []
        for idx, question in enumerate(questions[: req.num_questions], 1):
            qid = question.id.strip() or f"q{idx}"
            options = question.options

            if question.type == "true_false" and not options:
                if req.language.startswith("ko"):
                    options = ["참", "거짓"]
                else:
                    options = ["True", "False"]

            start = max(0.0, question.start)
            end = max(start, question.end)

            normalized.append(
                question.model_copy(
                    update={
                        "id": qid,
                        "options": options,
                        "start": start,
                        "end": end,
                    }
                )
            )
        return normalized

    def _build_source(self, req: QuizRequest, truncated: bool) -> QuizSource:
        if not req.segments:
            return QuizSource(segment_count=0, start=0.0, end=0.0, truncated=truncated)

        start = min(seg.start for seg in req.segments)
        end = max(seg.end for seg in req.segments)
        return QuizSource(
            segment_count=len(req.segments),
            start=start,
            end=end,
            truncated=truncated,
        )
