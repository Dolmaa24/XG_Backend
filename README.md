# AI HR Recruitment Simulator — Backend API

REST API backend for automated candidate screening: resume parsing, semantic job matching, AI-driven interviews, and weighted candidate ranking.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI + Python 3.11 |
| Database | PostgreSQL 16 + SQLAlchemy async |
| Auth | JWT (PyJWT) + bcrypt |
| NLP | spaCy en_core_web_sm |
| Matching | sentence-transformers (all-MiniLM-L6-v2) |
| AI Interview | Anthropic Claude / OpenAI GPT-4 |
| Task Queue | Celery + Redis |
| Container | Docker + Docker Compose |

---

## Local Setup

### 1. Clone and configure

```bash
cp .env.example .env
# Fill in SECRET_KEY, DATABASE_URL, ANTHROPIC_API_KEY (or OPENAI_API_KEY)
```

### 2. Run with Docker (recommended)

```bash
docker compose up --build
```

API available at: `http://localhost:8000`  
Interactive docs: `http://localhost:8000/docs`

### 3. Run locally (without Docker)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
uvicorn app.main:app --reload --port 8000
```

Start Celery worker (separate terminal):
```bash
celery -A app.tasks.celery_tasks.celery_app worker --loglevel=info
```

---

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/register` | None | Register candidate or HR user |
| POST | `/api/v1/auth/login` | None | Login, returns JWT |
| POST | `/api/v1/jobs/create` | HR | Create a job posting |
| GET | `/api/v1/jobs/` | Any | List all jobs |
| POST | `/api/v1/resume/upload` | Candidate | Upload resume PDF |
| GET | `/api/v1/resume/profile/{id}` | Owner/HR | Get parsed profile |
| POST | `/api/v1/match/score` | Any | Compute job match score |
| POST | `/api/v1/interview/start` | Candidate | Start AI interview |
| POST | `/api/v1/interview/respond` | Candidate | Submit answer |
| GET | `/api/v1/ranking/{job_id}` | HR | Get ranked candidates |
| GET | `/health` | None | Health check |

---

## Running Tests

```bash
pytest tests/ -v --asyncio-mode=auto
```

---

## Scoring Formula

```
final_score = (resume_score × weight_resume)
            + (match_score  × weight_match)
            + (interview_score × weight_interview)
```

Default weights: `30% / 30% / 40%` — configurable per job in the database.

---

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, lifespan, routers
│   ├── ai/                  # AI layer (integrated from XTRAGRAD-AI)
│   │   ├── config/          # AI settings (backed by core config)
│   │   ├── resume_parser/   # Education & experience extractors
│   │   ├── matching_engine/ # Skill + job match scoring
│   │   ├── interview_engine/# Rubric, interview config
│   │   ├── ranking_engine/  # Weighted scoring defaults
│   │   ├── prompts.py       # LLM prompt templates
│   │   └── docs/            # AI design documentation
│   ├── core/
│   │   ├── config.py        # All settings via pydantic-settings
│   │   ├── security.py      # JWT, bcrypt, RBAC
│   │   └── database.py      # Async SQLAlchemy engine
│   ├── models/models.py     # All 5 DB tables
│   ├── schemas/schemas.py   # All Pydantic request/response models
│   ├── api/v1/              # Route handlers
│   ├── services/            # Business logic (parser, matcher, interviewer, ranker)
│   ├── tasks/               # Celery background tasks
│   └── utils/               # File handler
├── tests/test_suite.py
├── tests/test_ai_layer.py   # AI layer integration tests
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## AI Layer Integration

The `app/ai/` package integrates the AI layer from [XTRAGRAD-AI commit e0bf2eb](https://github.com/XTRAGRAD-AI/AI-HR-Recruitment-Simulator/commit/e0bf2ebf297dcc00390d06f886de9f6e226ef963). Services delegate to AI modules while preserving all existing API contracts.

| Service | AI Module | Integration |
|---------|-----------|-------------|
| `parser.py` | `resume_parser/` | Supplements education/experience extraction |
| `matcher.py` | `matching_engine/` | Semantic + keyword matching, weighted blend |
| `interviewer.py` | `interview_engine/`, `prompts.py` | Rubric-driven LLM prompts |
| `ranker.py` | `ranking_engine/` | Centralized weighted scoring |

See `app/ai/README.md` for full AI layer documentation.

---

## Security Audit Log (Prompt 3)

| Severity | File | Issue | Fix Applied |
|---|---|---|---|
| CRITICAL | `auth.py` | No rate limiting on `/auth/login` — brute-force possible | `@limiter.limit` added to login + register |
| CRITICAL | `security.py` | No explicit token expiry enforcement | Explicit `exp` check added after `jwt.decode` |
| HIGH | `auth.py` | Login response time differs for wrong-password vs unknown-user — user enumeration risk | `DUMMY_HASH` always runs `verify_password` even when user not found |
| HIGH | `file_handler.py` | MIME check existed but null-byte injection in filename not guarded | Null-byte stripping + path confinement check added |
| HIGH | `file_handler.py` | Path traversal: sanitizer ran after traversal check — wrong order | Traversal check now runs before sanitization |
| HIGH | `interviewer.py` | Prompt injection list was ASCII-only — unicode lookalikes bypassed it | `unicodedata.normalize("NFKC")` applied before phrase matching |
| HIGH | `interviewer.py` | Job title and HR-supplied data embedded in system prompt unsanitized | `_sanitize_input()` applied to all prompt-injected values |
| MEDIUM | `interviewer.py` | `MAX_QUESTIONS`, `LLM_MAX_TOKENS`, `ANSWER_MAX_LENGTH` hardcoded as literals | Moved to `config.py` |
| MEDIUM | `matcher.py` | `SKILL_MATCH_THRESHOLD`, blend weights hardcoded | Moved to `config.py` |
| MEDIUM | `parser.py` | Single corrupt PDF page crashed entire parse job | Per-page try/except added — bad pages skipped |
| MEDIUM | `parser.py` | `SPACY_TEXT_CAP` hardcoded as `100_000` | Moved to `config.py` |
| MEDIUM | `interviewer.py` | LLM JSON parsing only stripped leading fences — trailing fences caused failures | Replaced with `_extract_json()` using regex + fallback |
| MEDIUM | `ranker.py` | LLM summary failure crashed ranking endpoint | Try/except with fallback summary added |
| LOW | `parser.py` | Image-only (scanned) PDF OCR fallback existed but zero-page edge case not handled | Zero-page guard added in both pdfplumber and fitz paths |

## Performance Fixes

| Issue | Fix |
|---|---|
| `SentenceTransformer` loaded per request | Loaded once at startup via `load_embedding_model()` |
| spaCy model loaded per request | Loaded once at startup via `load_spacy_model()` |
| N+1 query in `/ranking/{job_id}` | Single `JOIN` query: `select(Ranking, User).join(User)` |
| Skill embeddings computed in a loop | Replaced with single batch `model.encode(all_texts)` call |
| LLM summary generated even when unchanged | Summary invalidated only on score update; skipped if already present |
