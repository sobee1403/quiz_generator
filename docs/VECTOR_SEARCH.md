# 벡터 검색 가이드

## 1. 벡터 검색이란

저장된 **임베딩(벡터)**과 **쿼리 벡터**의 유사도(코사인 거리 등)로 정렬해, “의미적으로 가까운” 문서를 찾는 검색 방식이다.

- **Ingestion 시**: 강의 요약문을 OpenAI Embedding API로 벡터화해 `lecture_summary_embeddings.embedding`에 저장한다.
- **검색 시**: 검색하고 싶은 문장(예: 현재 강의 요약)을 한 번만 벡터화한 뒤, DB에서 그 벡터와 유사한 순으로 조회한다.

---

## 2. OpenAI 역할 (조회가 아님)

**벡터 검색 = OpenAI가 “조회”해 오는 것이 아니다.**

| 단계 | 담당 | 설명 |
|------|------|------|
| 쿼리 벡터 만들기 | **OpenAI** (1회) | 검색어/문장 한 개를 `EmbeddingService.embed(text)`로 벡터화. 이때만 Embedding API 호출. |
| 유사도 검색·조회 | **PostgreSQL + pgvector** | `ORDER BY embedding <=> :query_embedding::vector LIMIT k` 로 DB 안에 있는 벡터들과 비교해 상위 k건 반환. OpenAI 호출 없음. |

정리하면, **“검색해 오는 것”은 전부 DB**이고, OpenAI는 **검색어 1개를 벡터로 바꿀 때 한 번만** 사용한다.

---

## 3. 메타데이터 검색 vs 벡터 검색

### 메타데이터 검색

- **조건**: `course_id`, `lecture_id`, `user_id`, `id` 등으로 **어떤 행을 가져올지** 정확히 지정.
- **용도**: “이 강의 1건”, “이 강좌에서 id 순 이전 N개”처럼 **대상이 이미 정해진 경우**.
- **특징**: 구현 단순, 비용 없음(OpenAI 호출 없음). 지금의 “현재 1건 + 이전 전부(id 순)” 방식이 여기에 해당한다.

### 벡터 검색

- **조건**: 쿼리 문장을 벡터로 바꾼 뒤, DB에 저장된 벡터와 **유사도**로 정렬해 상위 k건 선택.
- **용도**: “지금 강의와 **의미적으로 비슷한** 이전 강의만 맥락으로 쓰고 싶을 때”, “사용자 질문과 가까운 강의만 검색”할 때.
- **특징**: 쿼리 1개당 Embedding API 1회 호출, 나머지는 DB 연산.

**메타데이터만으로 “이전 강의 전부 id 순”이면 충분하다면** 벡터 검색 없이도 동작에는 문제 없다.  
“의미적으로 관련 있는 이전 강의만 골라서” 맥락을 주고 싶을 때 벡터 검색을 켜면 된다.

---

## 4. 이 프로젝트에서의 활성화 방법

### 4.1 DB

- `lecture_summary_embeddings` 테이블에 `embedding vector(1536)` 컬럼과 ivfflat(cosine) 인덱스가 있으면 이미 준비된 상태다. (`db/init-vector.sql` 참고.)

### 4.2 Repository

- `LectureSummaryEmbeddingsRepo.get_similar_summaries(course_id, user_id, query_embedding, limit, exclude_lecture_id)`  
  - 같은 강좌·유저 내에서 `query_embedding`과 코사인 유사도가 높은 순으로 `(lecture_id, summary)` 리스트를 반환한다.  
  - 검색은 전부 DB(pgvector)에서 수행되며, `query_embedding`은 호출 전에 `EmbeddingService.embed(text)` 등으로 미리 만들어 두면 된다.

### 4.3 퀴즈 생성 시 “유사 이전 강의” 사용

- **기본(메타데이터)**: `get_previous_summaries(course_id, user_id, before_id)` → id 순 이전 요약 전부.
- **벡터 검색 사용**:  
  1. 현재 강의 요약 텍스트로 `embedding_service.embed(현재_요약)` **1회** 호출 → `query_embedding`.  
  2. `get_similar_summaries(course_id, user_id, query_embedding, limit=5, exclude_lecture_id=현재_lecture_id)` 호출.  
  3. 반환된 `(lecture_id, summary)` 리스트를 “이전 맥락”으로 프롬프트에 넣는다.

서비스/CLI에서는 `use_semantic_previous=True`(및 `semantic_limit`) 옵션으로 위 방식을 선택할 수 있다. 기본값은 기존처럼 메타데이터만 사용한다.

---

## 5. 사용 예시 (코드)

```python
# 퀴즈 생성 시 "의미적으로 비슷한 이전 강의"만 맥락으로 쓰기
from app.services.embedding import embedding_service
from app.db.repositories.lecture_summary_embeddings import lecture_summary_embeddings_repo

with get_session() as session:
    current = lecture_summary_embeddings_repo.get_lecture(session, course_id, lecture_id, user_id)
    current_summary = (current.summary or "").strip()
    query_embedding = embedding_service.embed(current_summary)  # OpenAI 1회
    similar = lecture_summary_embeddings_repo.get_similar_summaries(
        session, course_id, user_id, query_embedding, limit=5, exclude_lecture_id=lecture_id
    )
    previous_context = "\n\n---\n\n".join(s for _, s in similar)
```

CLI 예:

```bash
# 메타데이터만 사용 (기본)
python -m app.quiz_from_lecture_cli --course-id c1 --lecture-id l1 --user-id u1

# 벡터 검색으로 유사 이전 강의 5개만 맥락에 사용
python -m app.quiz_from_lecture_cli --course-id c1 --lecture-id l1 --user-id u1 --semantic-previous --semantic-limit 5
```

---

## 6. 참고

- 상세 RAG 파이프라인·개선 계획: [RAG_PIPELINE_REPORT.md](./RAG_PIPELINE_REPORT.md)
- Repository 구현: `app/db/repositories/lecture_summary_embeddings.py`
