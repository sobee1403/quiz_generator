"""
병렬 추출: Concept, Metadata, Difficulty (청크 텍스트 기준).
Concept: 강사가 준 제목(concept_hint)이 있으면 검증 후, 검증이 나쁘면 LLM이 보완·생성. 없으면 LLM 추출.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
        timeout=settings.REQUEST_TIMEOUT,
    )


def _extract_concept(text: str) -> str:
    """청크 내용만으로 LLM이 핵심 개념 한 문장 추출."""
    r = _get_client().chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.1,
        messages=[
            {"role": "system", "content": "주어진 강의 청크에서 핵심 개념(concept)을 한 문장으로 추출해 줘. 개념 이름만 짧게."},
            {"role": "user", "content": text[:3000]},
        ],
    )
    return (r.choices[0].message.content or "").strip()


def _validate_or_concept(text: str, concept_hint: str) -> str:
    """
    강사가 준 제목(concept_hint)을 검증. 내용과 잘 맞으면 그대로 반환하고,
    맞지 않으면 내용에 맞는 개념을 한 문장으로 만들어 반환. (제목을 중심으로 보완해도 됨)
    """
    r = _get_client().chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": (
                    "강사가 강의 제목(개념)으로 달아준 것이 아래 청크 내용과 맞는지 검증해 줘.\n"
                    "- 내용과 잘 맞으면 **제목을 그대로** 한 줄로만 출력해 줘.\n"
                    "- 내용과 맞지 않거나 제목이 너무 모호하면, 이 제목을 참고해서 내용에 맞는 핵심 개념을 한 문장으로 만들어 줘. (제목을 중심으로 보완해도 됨)\n"
                    "결과는 반드시 개념/제목 한 문장만 출력."
                ),
            },
            {
                "role": "user",
                "content": f"강사 제목: {concept_hint}\n\n청크 내용:\n{text[:3000]}",
            },
        ],
    )
    return (r.choices[0].message.content or "").strip()


def _extract_metadata(text: str) -> dict[str, Any]:
    r = _get_client().chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "주어진 강의 청크에서 메타데이터를 추출해 JSON으로 줘. 키: topics(배열), keywords(배열)."},
            {"role": "user", "content": text[:3000]},
        ],
    )
    raw = (r.choices[0].message.content or "{}").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"topics": [], "keywords": []}


def _extract_difficulty(text: str) -> str:
    r = _get_client().chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.1,
        messages=[
            {"role": "system", "content": "주어진 강의 청크의 난이도를 하나만 골라 줘: easy | medium | hard. 한 단어만 출력."},
            {"role": "user", "content": text[:3000]},
        ],
    )
    out = (r.choices[0].message.content or "").strip().lower()
    if out not in ("easy", "medium", "hard"):
        return "medium"
    return out


def extract_parallel(
    chunk_text: str,
    concept_hint: str | None = None,
) -> tuple[str, dict[str, Any], str]:
    """
    Concept, Metadata, Difficulty를 병렬로 추출해 (concept, metadata_dict, difficulty) 반환.
    concept_hint(강사가 달아준 강의 제목)가 있으면: 검증 후 쓰고, 검증이 나쁘면 LLM이 보완·생성.
    없으면: 청크에서 LLM이 개념 추출.
    """
    if concept_hint and concept_hint.strip():
        concept_fn = lambda: _validate_or_concept(chunk_text, concept_hint.strip())
    else:
        concept_fn = lambda: _extract_concept(chunk_text)

    with ThreadPoolExecutor(max_workers=3) as ex:
        f_concept = ex.submit(concept_fn)
        f_metadata = ex.submit(_extract_metadata, chunk_text)
        f_difficulty = ex.submit(_extract_difficulty, chunk_text)
        concept = f_concept.result()
        metadata = f_metadata.result()
        difficulty = f_difficulty.result()
    return concept, metadata, difficulty
