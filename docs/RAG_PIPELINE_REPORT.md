# RAG 파이프라인 레포트 및 개선 계획

## 1. 현재 RAG 파이프라인 개요

quiz_generator 서비스는 **강의 전사(transcript) → 요약·임베딩 저장 → 요약/전사 기반 퀴즈 생성** 흐름을 갖습니다. 전형적인 RAG의 Ingestion / Retrieval / Generation 단계와 대응됩니다.

### 1.1 파이프라인 구조

```
[Ingestion]  전사 JSON → 요약(LLM) → 임베딩(OpenAI) → DB 저장 (content, summary, embedding)
[Retrieval] (course_id, lecture_id, user_id)로 1건 조회 + 이전 강의 요약 목록 (id 순)
[Generation] 현재 강의 요약 + 이전 요약 + 현재 전사 일부 → 퀴즈 LLM → (선택) 검증 → (선택) lecture_quiz 저장
```

### 1.2 Ingestion (저장)

| 단계 | 담당 | 설명 |
|------|------|------|
| 입력 | CLI/API | 전사 JSON (`content`), `course_id`, `lecture_id`, `user_id`, 선택적으로 `course_title` 등 |
| 요약 | `SummaryService.summarize()` | 전사 텍스트를 LLM으로 2~4문장 요약. 제목(강좌/섹션/강의) 있으면 user 프롬프트에 포함 |
| 임베딩 | `EmbeddingService.embed()` | 요약문을 OpenAI text-embedding-3-small (1536차원)로 벡터화 |
| 저장 | `LectureSummaryEmbeddingsRepo.upsert()` | `lecture_summary_embeddings`에 content(JSON), summary(TEXT), embedding(vector) upsert |

- **청크 전략**: 강의 단위 1건 = 1요약 = 1임베딩. 세그먼트 단위 청킹/멀티벡터 저장 없음.
- **메타데이터**: `course_id`, `lecture_id`, `user_id`, `metadata`(JSONB) 저장.

### 1.3 Retrieval (조회)

| 방식 | 사용처 | 구현 |
|------|--------|------|
| 정확 조회 | 퀴즈 생성 시 “현재 강의” | `get_lecture(course_id, lecture_id, user_id)` — PK처럼 1건 반환 |
| 순서 기반 | “이전 강의 요약” 맥락 | `get_previous_summaries(course_id, user_id, before_id)` — `id < before_id`인 행의 summary만 id 오름차순 |

- **벡터 검색 미사용**: `embedding` 컬럼과 ivfflat 인덱스는 있으나, **유사도 검색(similarity search)을 하는 코드는 없음**. 조회는 모두 `course_id`/`lecture_id`/`user_id`/`id` 조건만 사용.

### 1.4 Generation (퀴즈 생성)

- **컨텍스트**: [이전 강의 요약들] + [현재 강의 요약] + [현재 강의 전사 일부(최대 8000자)].
- **프롬프트**: “현재 강의만으로 출제, 이전은 맥락만 참고” 명시.
- **출력**: JSON (질문, 5지선다, 정답 번호, 해설).
- **검증(선택)**: 문항별로 질문+보기만 주고 LLM이 정답 선택 → 출제 정답과 일치 시 `verified=true`.
- **저장(선택)**: `lecture_quiz` 테이블에 `questions`(JSONB) 등 저장.

---

## 2. RAG 관점에서의 강점·한계

### 2.1 강점

- **역할 분리**: Ingestion(store_lecture/API) / Retrieval(repo) / Generation(quiz_from_lecture)이 명확히 나뉨.
- **재현성**: 동일 강의·유저면 동일 (course_id, lecture_id, user_id)로 조회되므로, 퀴즈 생성 입력이 안정적.
- **맥락 제어**: “이전 강의만 참고”로 오답/혼선을 줄이기 좋음.
- **검증 단계**: LLM 정답 일치 검증으로 품질 신호 제공.

### 2.2 한계

1. **임베딩 미활용**  
   벡터는 저장만 하고 검색에 쓰지 않음. “질문/주제 기반 유사 강의 찾기”, “관련 이전 강의만 선택” 같은 시맨틱 검색이 불가.

2. **고정된 Retrieval 전략**  
   “현재 1건 + id 순 이전 전부”만 사용. 강의 수가 많을 때 토큰/비용·노이즈 증가, “가장 관련 있는 N개” 선택 불가.

3. **청크 단위 없음**  
   강의 전체를 하나의 요약·하나의 임베딩으로만 다룸. 구간별 퀴즈, 구간별 검색이 어렵다.

4. **에러/재시도·타임아웃**  
   LLM/임베딩 호출에 대한 재시도, 타임아웃 세분화, 실패 시 보존/재개 정책이 서비스 레이어에 거의 없음.

5. **관찰성**  
   토큰 사용량, 지연, 검색 결과 수 등 메트릭/로깅이 부족해 파이프라인 튜닝과 에이전트 설계에 불리함.

---

## 3. AI Agent 개발자 관점 보완 계획

에이전트가 “강의 RAG”를 안정적으로 활용·확장하려면 아래를 단계적으로 보완하는 것을 권장합니다.

### Phase 1: Retrieval 정교화 (벡터 검색 활성화)

**목표**: 저장된 임베딩을 실제로 쓰고, “관련 강의/요약”만 골라서 맥락으로 쓸 수 있게 한다.

| 항목 | 내용 |
|------|------|
| 1.1 유사도 검색 API | `lecture_summary_embeddings`에서 `course_id`(·`user_id`) 조건 하에 `embedding <=>` 쿼리로 상위 k건 조회하는 repository 메서드 추가. (pgvector cosine distance) |
| 1.2 퀴즈 생성 시 선택 전략 | 옵션으로 “이전 전부” 대신 “현재 강의 1건 + (현재 요약과) 유사도 상위 N개 요약”을 맥락으로 사용. 기존 동작은 `use_semantic_previous=False` 등으로 유지. |
| 1.3 인덱스/파라미터 | ivfflat lists 수, k 값은 강의 수·품질에 맞게 튜닝. 필요 시 HNSW 검토. |

**산출물**: `get_similar_summaries(course_id, user_id, embedding, limit, exclude_lecture_id?)`, 퀴즈 서비스에서 이 경로 사용 여부 플래그.

---

### Phase 2: Ingestion 보강 (청킹·메타데이터)

**목표**: 구간 단위 검색·출제와 에이전트의 “어디서 왔는지” 추적을 가능하게 한다.

| 항목 | 내용 |
|------|------|
| 2.1 청크 테이블/스키마 | 강의별 “청크”(예: 전사 세그먼트 N개 단위 또는 시간 구간)를 저장하는 테이블. (course_id, lecture_id, user_id, chunk_index, start_ts, end_ts, text, summary?, embedding, metadata) |
| 2.2 청크 단위 요약/임베딩 | 전사를 고정 길이 또는 구간 단위로 나누고, 청크별 요약(또는 원문 일부) + 임베딩 저장. 기존 “강의 1요약”은 유지해도 됨(강의 전체 요약용). |
| 2.3 메타데이터 | course_title, section_title, lecture_title, duration 등은 이미 있으면 metadata 또는 컬럼으로 저장해, Retrieval/Generation 시 필터·프롬프트에 활용. |

**산출물**: 청크 스키마, 청크 ingest 오케스트레이션(기존 store_lecture와 분리 또는 플래그로 선택).

---

### Phase 3: 안정성·관찰성 (에이전트 인프라)

**목표**: 에이전트가 장시간·다단계 파이프라인을 안전하게 돌리고, 문제를 진단할 수 있게 한다.

| 항목 | 내용 |
|------|------|
| 3.1 재시도·타임아웃 | LLM/임베딩 호출에 지수 백오프 재시도, 호출별 타임아웃 설정. 실패 시 상위 레이어에 명확한 예외/코드. |
| 3.2 토큰·지연 로깅 | 요청별 입력/출력 토큰 수, 지연 시간 로깅(구조화 로그 권장). 비용·지연 추적용. |
| 3.3 체크포인트/재개 | 대량 ingest 시 “마지막 성공 lecture_id” 등 저장해 중단 후 재개 가능하게 하거나, idempotent upsert 유지. |

**산출물**: 공통 HTTP/LLM 클라이언트 래퍼 또는 서비스 레이어 재시도/로깅, (선택) ingest 진행 상태 저장.

---

### Phase 4: 에이전트 활용 시나리오

**목표**: RAG를 “질문 답변”, “추천”, “자동 요약/퀴즈” 등 에이전트 작업에 연결한다.

| 항목 | 내용 |
|------|------|
| 4.1 Q&A/검색 API | 사용자 질문을 임베딩해 유사 청크(또는 강의 요약) 검색 후, 검색 결과만으로 LLM 답변 생성. (기존 퀴즈 생성과 별도 엔드포인트.) |
| 4.2 퀴즈 생성 트리거 | “이 강의 학습 완료 시 퀴즈 자동 생성·저장” 같은 규칙/에이전트 스텝에서 `POST /quiz/generate` + `save=true` 호출. |
| 4.3 승인·피드백 루프 | `lecture_quiz.approved` / `approved_at`를 활용해, “승인된 퀴즈만 노출” 또는 “승인률 기반 재생성 정책” 등 에이전트 정책에 반영. |

**산출물**: 검색 기반 Q&A 엔드포인트, (선택) 자동 퀴즈 생성·승인 플로우 명세.

---

## 4. 우선순위 요약

| 순서 | 단계 | 기대 효과 |
|------|------|-----------|
| 1 | Phase 1: 벡터 검색 활성화 | 이미 쌓은 임베딩 활용, 맥락 품질·확장성 개선 |
| 2 | Phase 3: 재시도·로깅 | 에이전트/운영 안정성, 비용·지연 가시화 |
| 3 | Phase 2: 청킹 | 구간 단위 검색·출제, 더 세밀한 RAG |
| 4 | Phase 4: Q&A·자동화 | 에이전트 시나리오 직접 연결 |

이 순서로 적용하면, 현재 파이프라인을 유지하면서 단계적으로 “진짜 RAG”와 에이전트 친화적인 구조로 보완할 수 있습니다.
