"""
전사 JSON을 LLM으로 요약하는 서비스.
"""

from typing import Any

from openai import OpenAI

from app.core.config import settings


def _transcript_from_content(content_json: dict[str, Any], max_chars: int | None = None) -> str:
    """전사 JSON의 segments를 한 덩어리 텍스트로 만든다."""
    segments = content_json.get("segments") or []
    lines: list[str] = []
    for seg in segments:
        if isinstance(seg, dict) and seg.get("text"):
            speaker = seg.get("speaker")
            prefix = f"[{speaker}] " if speaker else ""
            lines.append(prefix + seg["text"].strip())
    transcript = "\n".join(lines)
    if max_chars and len(transcript) > max_chars:
        transcript = transcript[:max_chars]
    return transcript


class SummaryService:
    """강의 전사 텍스트를 요약문으로 만든다."""

    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.REQUEST_TIMEOUT,
        )

    def summarize(
        self,
        content_json: dict[str, Any],
        max_transcript_chars: int | None = None,
        *,
        course_title: str | None = None,
        section_title: str | None = None,
        lecture_title: str | None = None,
    ) -> str:
        """
        전사 JSON에서 텍스트를 뽑아 LLM으로 요약한 문자열을 반환한다.
        max_transcript_chars: 요약에 넣을 전사 최대 글자 수 (None이면 설정값 또는 제한 없음)
        course_title/section_title/lecture_title: 강좌 대주제·소주제로 프롬프트(user)에 포함.
        """
        limit = max_transcript_chars or settings.MAX_TRANSCRIPT_CHARS
        transcript = _transcript_from_content(content_json, max_chars=limit)
        if not transcript.strip():
            return ""

        system_prompt = (
            "너는 강의 또는 발표 전사 내용을 읽고 짧은 요약문을 만드는 전문가다. "
            "2~4문장 정도로 핵심만 간결하게 요약한다. 요약만 출력하고 다른 설명은 하지 마라."
        )
        # 맥락(강좌/섹션/강의 제목)은 이번 입력의 데이터이므로 user 메시지에 포함
        title_lines: list[str] = []
        if course_title and course_title.strip():
            title_lines.append(f"강좌(대주제): {course_title.strip()}")
        if section_title and section_title.strip():
            title_lines.append(f"섹션: {section_title.strip()}")
        if lecture_title and lecture_title.strip():
            title_lines.append(f"강의: {lecture_title.strip()}")
        if title_lines:
            context = "\n".join(title_lines) + "\n\n"
        else:
            context = ""
        user_prompt = f"{context}아래 전사 내용을 요약해 줘.\n\n전사:\n{transcript}"

        response = self._client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=settings.OPENAI_TEMPERATURE,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        summary = (response.choices[0].message.content or "").strip()
        return summary


summary_service = SummaryService()
