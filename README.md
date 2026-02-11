# 퀴즈 생성 도구

시간 단위로 세그먼테이션된 강의 전사 JSON을 받아 퀴즈를 생성하는 Python CLI 도구입니다.

**흐름 구분**
- **Ingestion 파이프라인 (업로드 → 큐 → 워커)**: 음성/전사 업로드 시 이벤트로 job 적재 → Async Worker가 STT → Span Chunking → Concept/Metadata/Difficulty 병렬 추출 → Vector Store + SQL 저장. `POST /lectures/upload` 또는 `POST /lectures/ingestion/enqueue`, `python -m app.worker` 참고.
- **DB·요약 기반 퀴즈**: 전사를 DB에 저장한 뒤, 강의별 요약을 기준으로 퀴즈 생성. `python -m app.quiz_from_lecture_cli` 또는 `POST /quiz/generate` 사용.
- **Legacy (전사 직접)**: DB 없이 전사 JSON만 넣고 한 번에 퀴즈 생성. `python app.main.py` 또는 `python -m app.main` 사용.

## 준비

1) PostgreSQL (pgvector) 실행

```bash
cd quiz_generator
docker-compose up -d
```

2) 벡터 DB 세팅 (최초 1회)

컨테이너가 떠 있는 상태에서 아래 중 하나로 실행하세요.

```bash
# 방법 A: init SQL 파일 적용
docker exec -i lxp5 psql -U app -d appdb < db/init-vector.sql

# 방법 B: 컨테이너 안에서 psql로 접속 후 수동 실행
docker exec -it lxp5 psql -U app -d appdb
# psql 프롬프트에서: \i /path/to/db/init-vector.sql (호스트 경로가 아니라 컨테이너 내부 경로 필요)
# 또는 방법 A 권장
```

- `db/init-vector.sql`: pgvector 확장, `lecture_summary_embeddings`, `ingestion_jobs`, `lecture_chunks`, `lecture_chunk_vectors` 테이블 생성

3) 환경 변수 설정
- `quiz_generator/.env.example`를 복사해서 `.env`를 만들고 API 키를 채워주세요.

```
PROJECT_NAME=Quiz-Generator
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4o-mini
OPENAI_TEMPERATURE=0.2
DATABASE_URL=postgresql://app:apppw@localhost:5432/appdb
```

4) 의존성 설치 (uv 사용 예시)
```
cd quiz_generator
uv venv
uv pip install -e .
```

5) 테스트 (선택) — acc 전사로 store → 퀴즈 생성
```
uv pip install -e ".[dev]"
pytest tests/ -v
```
- `tests/test_lecture_pipeline.py`: acc의 `1.aac.raw.json` ~ `5.aac.raw.json`을 차례로 저장한 뒤, 각 강의에 대해 퀴즈 생성·검증 스키마 검사. DB·OpenAI 필요.

## 강의 전사 → DB 저장 (lecture_summary_embeddings)

전사 JSON(원문)을 `content`에, 요약문을 임베딩해 `embedding`에 넣어 저장합니다.

```bash
python -m app.store_lecture \
  --input ../acc/transcripts/gpt-4o-transcribe-diarize/1.aac.raw.json \
  --course-id course1 --lecture-id lecture1 --user-id user1 \
  --summary "이 강의는 도커와 컨테이너 기반 개발 환경에 대해 설명한다."
```

- 패키지: `app.db`(연결·repository), `app.services`(임베딩·저장 오케스트레이션), `app.store_lecture`(CLI).
- **로그**: stderr로 출력되므로 터미널에서 바로 확인 가능. JSON 결과(stdout)와 분리됨.

### 요약 자동 생성해서 저장 (--summary 생략)

```bash
python -m app.store_lecture \
  --input ../acc/transcripts/gpt-4o-transcribe-diarize/1.aac.raw.json \
  --course-id course1 --lecture-id lecture1 --user-id user1
```

- 요약 시 맥락 반영: `--course-title`, `--section-title`, `--lecture-title` 옵션을 주면 LLM 요약 프롬프트에 포함됩니다.

## 요약 기준 퀴즈 생성 (검증 포함)

해당 강의 요약 + 이전 강의 요약만 참고해 퀴즈 생성 후, 문항별 검증(LLM이 정답 고르기 → 일치 시 `verified: true`).

```bash
# 기본: 검증 포함, 로그는 stderr / JSON은 stdout
python -m app.quiz_from_lecture_cli \
  --course-id course1 --lecture-id lecture1 --user-id user1 \
  --num-questions 5 --pretty
```

- **로그 조회**: 위 명령 실행 시 stderr에 `[INFO]` 로그가 출력됨. (DB 조회, 이전 요약 N건, LLM 호출, 문항별 검증 결과 등)
- **검증 생략**: `--no-validate` 추가 시 `verified` 필드 없이 생성만 반환.

```bash
# 로그(stderr) + JSON(stdout) 둘 다 화면에 보기 (기본)
python -m app.quiz_from_lecture_cli --course-id c1 --lecture-id l1 --user-id u1 --pretty

# JSON만 파일로 저장하고 로그는 화면에만 출력
python -m app.quiz_from_lecture_cli --course-id c1 --lecture-id l1 --user-id u1 --pretty > quiz.json

# 로그와 JSON 전체를 파일에 남기기
python -m app.quiz_from_lecture_cli --course-id c1 --lecture-id l1 --user-id u1 --pretty 2>&1 | tee quiz.log
```

### 맥락을 “처음 N개 강의”로만 제한 (6번 이후 미반영)

총 30개 강의가 있어도 **1~5번 강의 정보만** 맥락에 넣고, 6번 이후는 반영하지 않으려면 `--max-context-lectures=5` 를 사용한다.  
(저장 순서가 강의 순서와 같다고 가정하며, id 순 “처음 N개” 강의만 조회한다.)

```bash
# id 순 처음 5개 강의 요약만 맥락에 사용 (6번 이후 내용 미반영)
python -m app.quiz_from_lecture_cli --course-id c1 --lecture-id l1 --user-id u1 --max-context-lectures 5 --pretty
```

### 벡터 검색(유사 이전 강의만 맥락으로 사용)

기본은 **메타데이터(id 순)** 로 “이전 강의 요약 전부”를 맥락에 넣는다.  
**의미적으로 비슷한** 이전 강의 요약만 쓰려면 `--semantic-previous`를 사용한다. (자세한 개념·OpenAI 역할: [docs/VECTOR_SEARCH.md](docs/VECTOR_SEARCH.md))

```bash
# 유사도 상위 5건만 이전 맥락으로 사용 (쿼리 임베딩 1회 + DB 벡터 검색)
python -m app.quiz_from_lecture_cli --course-id c1 --lecture-id l1 --user-id u1 --semantic-previous --semantic-limit 5 --pretty
```

## Ingestion 파이프라인 (Upload → Queue → Worker)

업로드 이벤트로 job을 큐에 적재하고, 별도 워커가 STT → Span Chunking → Concept/Metadata/Difficulty 병렬 추출 → Vector Store + SQL 저장을 수행한다.

1. **업로드(음성)** → job 적재: `POST /lectures/upload` (multipart: course_id, lecture_id, user_id, file, 선택: concept_hint 또는 lecture_title)
2. **전사 JSON 적재**: `POST /lectures/ingestion/enqueue` (JSON: course_id, lecture_id, user_id, transcript 또는 content, 선택: concept_hint 또는 lecture_title)
3. **Job 상태 조회**: `GET /lectures/ingestion/jobs/{job_id}`
4. **Async Worker 실행** (큐 폴링 후 처리):

```bash
python -m app.worker
```

- Worker는 `ingestion_jobs` 테이블에서 status=pending인 job을 폴링해, STT(음성인 경우) → Span Chunking → 청크별 Concept/Metadata/Difficulty 병렬 추출 → `lecture_chunks`(SQL) + `lecture_chunk_vectors`(Vector Store)에 저장한다.
- **Concept**: 강사가 `concept_hint`(또는 `lecture_title`)로 제목을 주면, 청크 내용과 맞는지 검증하고 맞으면 그대로 사용·나쁘면 LLM이 보완해 사용. 없으면 청크에서 LLM이 개념 추출.

## API (FastAPI)

강의 요약·저장, Ingestion 큐, 퀴즈 생성을 HTTP API로 제공한다.

```bash
uv run uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

- **Swagger UI**: http://localhost:8000/docs

### POST /lectures/upload (강의 음성 업로드 → Ingestion Job Enqueue)

- multipart: `course_id`, `lecture_id`, `user_id`, `file`(음성 파일), 선택: `concept_hint` 또는 `lecture_title`(강사 제목)
- Response: `job_id`, `message`

### POST /lectures/ingestion/enqueue (전사 JSON → Job Enqueue)

- Body: `course_id`, `lecture_id`, `user_id`, `transcript` 또는 `content` (segments 포함 JSON), 선택: `concept_hint` 또는 `lecture_title`(강사 제목)
- Response: `job_id`, `message`

### GET /lectures/ingestion/jobs/{job_id} (Job 상태)

- Response: `job_id`, `status`(pending|processing|done|failed), `error_message?`

### POST /lectures/summarize-and-store (강의 요약 및 저장)

전사 JSON을 받아 요약 생성 후 `lecture_summary_embeddings`에 저장.  
`course_title`(강좌 대주제), `section_title`, `lecture_title`(소주제)를 주면 요약 LLM **user 메시지**에 포함되어 맥락으로 사용된다.

- Body: `content`(전사 JSON), `course_id`, `lecture_id`, `user_id`, `course_title?`, `section_title?`, `lecture_title?`, `summary?`(있으면 LLM 생략)
- Response: `summary`, `message`

### POST /quiz/generate (퀴즈 생성)

해당 강의 요약 기준으로 퀴즈 생성. 선택 시 검증(`verified`) 및 `lecture_quiz` 저장.

- Body: `course_id`, `lecture_id`, `user_id`, `num_questions?`(기본 5), `save?`, `validate?`, `use_semantic_previous?`, `semantic_limit?`, `max_context_lectures?`(맥락을 id 순 처음 N개 강의로 제한, 예: 5면 6번 이후 미반영)
- Response: `questions`, `saved`

## 실행 (Legacy 퀴즈 CLI — 전사 직접)

DB 없이 전사 JSON만으로 퀴즈 생성할 때 사용.

```
python app/main.py --input ../acc/transcripts/gpt-4o-transcribe-diarize/1.aac.normalized.json \
  --num-questions 5 \
  --question-types multiple_choice,true_false \
  --language ko \
  --difficulty medium \
  --pretty
```

## 사용 예시

### 1) 파일 입력 → stdout 출력
```
python app/main.py --input ../acc/transcripts/gpt-4o-transcribe-diarize/1.aac.normalized.json --pretty
```

### 2) stdin 입력 → 파일 출력
```
cat ../acc/transcripts/gpt-4o-transcribe-diarize/1.aac.normalized.json | \
  python app/main.py --stdin --output ./quiz.json --pretty
```

## 입력 JSON 형식

`acc/transcripts/gpt-4o-transcribe-diarize/*.normalized.json` 형식을 그대로 지원합니다.
```
{
  "meta": { "model": "...", "audio_id": "...", "created_at": "..." },
  "segments": [
    { "text": "...", "start": 0.0, "end": 3.1, "speaker": "A" }
  ]
}
```

## 응답 형식
```
{
  "title": "도커 입문 퀴즈",
  "language": "ko",
  "questions": [
    {
      "id": "q1",
      "type": "multiple_choice",
      "question": "...",
      "options": ["...", "...", "...", "..."],
      "answer": "...",
      "explanation": "...",
      "start": 193.2,
      "end": 196.0
    }
  ],
  "source": {
    "segment_count": 42,
    "start": 0.05,
    "end": 233.25,
    "truncated": false
  }
}
```
