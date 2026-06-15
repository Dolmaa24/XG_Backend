"""
Test harness: runs the app against an in-memory SQLite DB with the AI layer,
LLM, Redis, and resume parsing mocked — so the full /api contract is exercised
without Postgres, Redis, torch, or spaCy models.
"""
import os
import uuid
import tempfile

os.environ.setdefault("SECRET_KEY", "test-secret-key-at-least-32-characters-long")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("AI_SERVICE_ENABLED", "false")
os.environ.setdefault("DEBUG", "false")
os.environ.setdefault("LOCAL_UPLOAD_DIR", os.path.join(tempfile.gettempdir(), "aihr_test_uploads"))
# Effectively disable rate limiting during tests (many registrations per minute).
os.environ.setdefault("LOGIN_RATE_LIMIT", "100000/minute")
os.environ.setdefault("UPLOAD_RATE_LIMIT", "100000/minute")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.core import security
from app.services import ai_client, resume_jobs

# The engine/session factory is created per-test (in the test's event loop) so the
# in-memory SQLite connection isn't shared across pytest-asyncio's per-test loops.
_SessionFactory = None


async def _override_get_db():
    async with _SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = _override_get_db


# ── Fake Redis for token-revocation blocklist ─────────────────────────────────
class _FakeRedis:
    def __init__(self):
        self.store: set[str] = set()

    async def set(self, key, value, ex=None):
        self.store.add(key)

    async def exists(self, key):
        return 1 if key in self.store else 0


_fake_redis = _FakeRedis()


@pytest_asyncio.fixture(autouse=True)
async def _setup(monkeypatch):
    global _SessionFactory
    # Fresh engine in THIS test's event loop.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _SessionFactory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Patch the Redis blocklist client.
    monkeypatch.setattr(security, "_get_redis", lambda: _fake_redis)
    _fake_redis.store.clear()

    # Deterministic AI stubs (no torch / no LLM / no network).
    async def fake_match(candidate_skills, job_skills, candidate_text="", job_description=""):
        matched = [s for s in job_skills if s in candidate_skills]
        missing = [s for s in job_skills if s not in candidate_skills]
        score = round(len(matched) / len(job_skills) * 100, 2) if job_skills else 0.0
        return {"match_score": score, "matched_skills": matched, "missing_skills": missing}

    async def fake_skill_analysis(skills, target_skills):
        gaps = [t for t in target_skills if t not in skills]
        return {"strengths": list(skills), "gaps": gaps,
                "skill_levels": {s: "intermediate" for s in skills},
                "recommendations": [f"Learn {g}" for g in gaps[:3]]}

    async def fake_recommend_jobs(candidate_skills, jobs):
        return [{"job_id": j["job_id"], "title": j["title"], "score": 80.0,
                 "matched_skills": candidate_skills, "missing_skills": [], "reasons": ["stub"]}
                for j in jobs]

    async def fake_recommend_candidates(job, candidates):
        return sorted(
            [{"user_id": c["user_id"], "name": c.get("name", ""),
              "final_score": c.get("final_score", 0.0), "summary": c.get("summary")} for c in candidates],
            key=lambda c: c["final_score"], reverse=True)

    async def fake_first_q(job_title, required_skills, candidate_profile):
        return {"question": "Tell me about your experience.", "category": "technical"}

    async def fake_eval(job_title, required_skills, candidate_profile, conversation, latest_answer, question_index=0):
        return {"answer_score": 80.0, "feedback": "Good answer.",
                "next_question": None, "interview_complete": True}

    monkeypatch.setattr(ai_client, "match", fake_match)
    monkeypatch.setattr(ai_client, "skill_analysis", fake_skill_analysis)
    monkeypatch.setattr(ai_client, "recommend_jobs", fake_recommend_jobs)
    monkeypatch.setattr(ai_client, "recommend_candidates", fake_recommend_candidates)
    monkeypatch.setattr(ai_client, "interview_first_question", fake_first_q)
    monkeypatch.setattr(ai_client, "interview_evaluate", fake_eval)

    # Resume parsing runs as an async background job; stub it to a no-op here
    # (the real parser is unit-tested separately, and runs against Postgres in prod).
    async def fake_parse(resume_id, file_path):
        return None

    # Patch at the source AND at both import sites (routers import the name directly).
    monkeypatch.setattr(resume_jobs, "parse_and_store", fake_parse)
    from app.api import resume_candidate, resumes_admin
    monkeypatch.setattr(resume_candidate, "parse_and_store", fake_parse)
    monkeypatch.setattr(resumes_admin, "parse_and_store", fake_parse)

    yield

    await engine.dispose()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Helpers ───────────────────────────────────────────────────────────────────
async def register_and_login(client, role="candidate"):
    email = f"{role}_{uuid.uuid4().hex[:8]}@test.com"
    password = "TestPass1234!"
    reg = await client.post("/api/auth/register", json={
        "name": f"Test {role}", "email": email, "password": password, "role": role})
    user_id = reg.json()["id"]
    res = await client.post("/api/auth/login", json={"email": email, "password": password})
    return {"id": user_id, "email": email, "token": res.json()["access_token"]}


def auth(token):
    return {"Authorization": f"Bearer {token}"}
