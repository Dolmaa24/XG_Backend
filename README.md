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

## API

The public API follows the frontend contract under the `/api` prefix, split into
an **Admin Dashboard** and a **Candidate Dashboard**. Full interactive docs at
`/docs`. `auth` (`admin`/`hr`) is staff; `candidate` endpoints allow the resource
owner or staff. List endpoints are paginated (`?page=&limit=`) and return
`{ items, total, page, limit }`.

### Admin Dashboard
| Method | Path | Auth |
|---|---|---|
| POST | `/api/auth/login` | None |
| POST | `/api/auth/logout` | Any (revokes token) |
| POST | `/api/auth/register` | None |
| GET | `/api/admin/profile` | Staff |
| GET | `/api/candidates` · `/api/candidates/search?q=` · `/api/candidates/{id}` | Staff |
| DELETE | `/api/candidates/{id}` | Staff |
| POST | `/api/resumes/upload` | Staff |
| GET | `/api/resumes` · `/api/resumes/{id}` · `/api/resumes/download/{id}` | Staff |
| DELETE | `/api/resumes/{id}` | Staff |
| POST · GET | `/api/jobs` | Staff · Any |
| PUT · DELETE | `/api/jobs/{id}` | Staff |
| GET | `/api/match-results` | Staff |
| GET | `/api/ai/recommendations` | Staff |
| GET | `/api/interviews` | Staff |
| GET | `/api/dashboard/summary` · `/activity` · `/progress` | Staff |
| GET | `/api/analytics/skills` · `/status` · `/match-scores` · `/interview-performance` | Staff |

### Candidate Dashboard
| Method | Path | Auth |
|---|---|---|
| GET · PUT | `/api/profile/{userId}` | Owner/Staff |
| POST | `/api/profile` · `/api/profile/upload-avatar` | Owner/Staff |
| POST | `/api/resume/upload` | Candidate |
| GET | `/api/resume/{userId}` | Owner/Staff |
| PUT · DELETE | `/api/resume/{resumeId}` | Owner/Staff |
| GET | `/api/ai/skill-analysis/{userId}` | Owner/Staff |
| GET | `/api/jobs/recommendations/{userId}` · `/api/jobs/search?query=` | Owner/Staff · Any |
| GET | `/api/applications/{userId}` | Owner/Staff |
| POST · DELETE | `/api/applications/apply` · `/api/applications/{id}` | Owner/Staff |
| GET | `/api/interviews/status/{userId}` | Owner/Staff |
| POST | `/api/mock-interview/start` · `/submit` | Candidate |
| GET | `/api/mock-interview/questions` | Any |
| GET | `/api/assessment/start` · `/api/assessment/result/{userId}` | Candidate · Owner/Staff |
| POST | `/api/assessment/submit` | Candidate |
| GET · PUT | `/api/settings/{userId}` | Owner/Staff |
| GET | `/api/search/jobs?query=` | Any |
| GET | `/health` | None |

### AI integration
AI-powered features (parsing, matching, interviews, recommendations, skill
analysis, assessments) route through `app/services/ai_client.py`. With
`AI_SERVICE_ENABLED=true` it calls the AI team's microservice at `AI_SERVICE_URL`;
otherwise (or on error/timeout) it falls back to the backend's own local services.
See [docs/AI_INTEGRATION_CONTRACT.md](docs/AI_INTEGRATION_CONTRACT.md).

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
│   ├── core/
│   │   ├── config.py        # All settings via pydantic-settings
│   │   ├── security.py      # JWT, bcrypt, RBAC
│   │   └── database.py      # Async SQLAlchemy engine
│   ├── models/models.py     # DB tables (users, jobs, resumes, interviews, rankings,
│   │                        #   profiles, applications, settings, assessments, mock_interviews)
│   ├── schemas/schemas.py   # All Pydantic request/response models
│   ├── api/                 # Route handlers (16 routers under /api)
│   ├── services/            # parser, matcher, interviewer, ranker, ai_client,
│   │                        #   aggregations, assessment, resume_jobs
│   ├── tasks/               # Celery background tasks (optional; parsing also runs in-process)
│   └── utils/               # File handler
├── tests/test_suite.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

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
