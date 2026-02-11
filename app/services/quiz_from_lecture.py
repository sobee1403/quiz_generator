"""
요약 기준 퀴즈 생성: 해당 강의 요약을 기준으로, 이전 강의 요약만 참고, 이후 강의 내용 미포함.
출력: 질문, 선택지 5개, 정답(1~5), 해설.
"""

import logging
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.db.connection import get_session
from app.db.repositories.lecture_quiz import lecture_quiz_repo
from app.db.repositories.lecture_summary_embeddings import lecture_summary_embeddings_repo
from app.schema.quiz_lecture import QuizFromLectureResponse, ValidatedQuizFromLectureResponse
from app.services.embedding import embedding_service
from app.services.quiz_validator import quiz_validator_service
from app.services.summary import summary_service


def _transcript_from_content(content_json: dict[str, Any], max_chars: int = 8000) -> str:
    """전사 JSON의 segments를 한 덩어리 텍스트로 만든다."""
    segments = content_json.get("segments") or []
    lines: list[str] = []
    for seg in segments:
        if isinstance(seg, dict) and seg.get("text"):
            lines.append(seg["text"].strip())
    transcript = "\n".join(lines)
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars]
    return transcript


class QuizFromLectureService:
    """해당 강의 요약 + 이전 요약 참고로 퀴즈 생성 (이후 강의 내용 미포함)."""

    def __init__(self) -> None:
        self._client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            timeout=settings.REQUEST_TIMEOUT,
        )

    def generate(
        self,
        course_id: str,
        lecture_id: str,
        user_id: str,
        num_questions: int = 5,
        use_semantic_previous: bool = False,
        semantic_limit: int = 5,
        max_context_lectures: int | None = None,
    ) -> QuizFromLectureResponse:
        """
        DB에서 해당 강의 + 이전 강의 요약을 꺼내어, 현재 강의 기준으로만 퀴즈 생성.

        use_semantic_previous=True 이면 id 순 이전 전부 대신, 현재 요약과 유사도 높은
        이전 강의 요약만 semantic_limit 건만 맥락으로 사용(벡터 검색, docs/VECTOR_SEARCH.md 참고).
        max_context_lectures=N 이면 id 순 처음 N개 강의의 요약만 맥락에 사용(예: 5면 1~5번만, 6번 이후 미반영).
        """
        with get_session() as session:
            logger.info("DB에서 강의 조회 중 course_id=%s lecture_id=%s user_id=%s", course_id, lecture_id, user_id)
            current = lecture_summary_embeddings_repo.get_lecture(
                session, course_id, lecture_id, user_id
            )
            if not current:
                raise ValueError(
                    f"강의를 찾을 수 없음: course_id={course_id}, lecture_id={lecture_id}, user_id={user_id}"
                )
            current_summary = (current.summary or "").strip()
            if not current_summary:
                logger.info("DB에 요약 없음 → 전사에서 요약 생성 후 퀴즈 생성")
                current_summary = summary_service.summarize(current.content)

            if use_semantic_previous and current.embedding:
                query_embedding = current.embedding
                similar = lecture_summary_embeddings_repo.get_similar_summaries(
                    session, course_id, user_id, query_embedding, limit=semantic_limit, exclude_lecture_id=lecture_id
                )
                previous_summaries = [s for _, s in similar]
                logger.info("벡터 검색으로 유사 이전 강의 요약 %d건 참고", len(previous_summaries))
            elif use_semantic_previous:
                query_embedding = embedding_service.embed(current_summary)
                similar = lecture_summary_embeddings_repo.get_similar_summaries(
                    session, course_id, user_id, query_embedding, limit=semantic_limit, exclude_lecture_id=lecture_id
                )
                previous_summaries = [s for _, s in similar]
                logger.info("벡터 검색으로 유사 이전 강의 요약 %d건 참고 (쿼리 임베딩 1회 호출)", len(previous_summaries))
            else:
                previous_summaries = []
                if current.id is not None:
                    if max_context_lectures is not None and max_context_lectures > 0:
                        previous_summaries = lecture_summary_embeddings_repo.get_summaries_from_first_n_lectures(
                            session, course_id, user_id, first_n=max_context_lectures, before_id=current.id
                        )
                        logger.info(
                            "이전 강의 요약 %d건 참고 (id 순 처음 %d개 강의만, 6번 이후 미반영)",
                            len(previous_summaries),
                            max_context_lectures,
                        )
                    else:
                        previous_summaries = lecture_summary_embeddings_repo.get_previous_summaries(
                            session, course_id, user_id, before_id=current.id
                        )
                        logger.info("이전 강의 요약 %d건 참고 (메타데이터/id 순)", len(previous_summaries))

            current_transcript = _transcript_from_content(current.content)
            previous_context = "\n\n---\n\n".join(previous_summaries) if previous_summaries else "(없음)"

        system_prompt = """너는 강의 요약과 전사를 보고 학습용 퀴즈를 만드는 전문가다.
- 퀴즈는 **현재 강의**의 요약/전사 내용만 기준으로 만든다.
- 이전 강의 요약은 맥락 참고용으로만 쓰고, 퀴즈 지문에 이전·이후 강의 내용을 넣지 마라.
- 각 문항은 반드시 질문 1개, 선택지 5개(1~5번), 정답(1~5 중 하나), 해설을 포함한다.
- 출력은 반드시 아래 JSON 형식만 반환한다. 다른 텍스트는 포함하지 마라."""

        user_prompt = f"""
[이전 강의 요약들 - 참고만 할 것]
{previous_context}

[현재 강의 요약]
{current_summary}

[현재 강의 전사 일부 - 퀴즈 출제 기준]
{current_transcript}

위 **현재 강의** 내용만 바탕으로 객관식 퀴즈 {num_questions}문항을 만들어 줘.
각 문항: question(질문), options(선택지 5개, 순서대로 1번~5번), answer(정답 번호 1~5), explanation(해설).
JSON만 출력해.

형식:
{{"questions": [{{"question": "...", "options": ["1번 선택지", "2번", "3번", "4번", "5번"], "answer": 1, "explanation": "..."}}, ...]}}
""".strip()

        logger.info("LLM 퀴즈 생성 호출 중 (문항 수=%d)", num_questions)
        response = self._client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=settings.OPENAI_TEMPERATURE,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        result = QuizFromLectureResponse.model_validate_json(raw)
        logger.info("퀴즈 생성 완료 수신 문항 수=%d", len(result.questions))
        return result

    def generate_validated(
        self,
        course_id: str,
        lecture_id: str,
        user_id: str,
        num_questions: int = 5,
        use_semantic_previous: bool = False,
        semantic_limit: int = 5,
        max_context_lectures: int | None = None,
    ) -> ValidatedQuizFromLectureResponse:
        """
        퀴즈 생성 후 검증 파이프라인: 각 문항에 대해 질문+보기만 주고 LLM이 정답을 고르게 한 뒤,
        생성 시 정답과 일치하면 verified=True. 검증된 결과만 반환.
        """
        raw = self.generate(
            course_id, lecture_id, user_id, num_questions,
            use_semantic_previous=use_semantic_previous,
            semantic_limit=semantic_limit,
            max_context_lectures=max_context_lectures,
        )
        logger.info("검증 단계 시작")
        return quiz_validator_service.validate_all(raw)

    def save_result(
        self,
        course_id: str,
        lecture_id: str,
        result: QuizFromLectureResponse | ValidatedQuizFromLectureResponse,
    ) -> None:
        """퀴즈 생성(또는 검증) 결과를 DB에 저장. JSON 그대로 저장(question, options, answer, explanation 등)."""
        questions_data = [q.model_dump() for q in result.questions]
        with get_session() as session:
            lecture_quiz_repo.insert(
                session,
                course_id=course_id,
                lecture_id=lecture_id,
                questions=questions_data,
            )
        logger.info(
            "퀴즈 결과 저장 완료 course_id=%s lecture_id=%s 문항 수=%d",
            course_id,
            lecture_id,
            len(questions_data),
        )


quiz_from_lecture_service = QuizFromLectureService()
