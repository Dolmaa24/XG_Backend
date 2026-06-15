"""
Endpoint tests for the full /api frontend contract.
AI layer, LLM, Redis, and resume parsing are mocked in conftest.py.
Run: pytest tests/ -v
"""
import io
import uuid
import pytest


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def register_and_login(client, role="candidate"):
    email = f"{role}_{uuid.uuid4().hex[:8]}@test.com"
    password = "TestPass1234!"
    reg = await client.post("/api/auth/register", json={
        "name": f"Test {role}", "email": email, "password": password, "role": role})
    assert reg.status_code == 201, reg.text
    user_id = reg.json()["id"]
    res = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return {"id": user_id, "email": email, "token": res.json()["access_token"]}


async def make_job(client, token):
    res = await client.post("/api/jobs", headers=auth(token), json={
        "title": "Python Backend Engineer",
        "description": "Looking for a Python developer with FastAPI experience.",
        "required_skills": ["python", "fastapi", "docker"], "experience_years": 2})
    assert res.status_code == 201, res.text
    return res.json()["id"]


# ── Auth & RBAC ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_returns_token_and_user(client):
    admin = await register_and_login(client, "admin")
    me = await client.get("/api/admin/profile", headers=auth(admin["token"]))
    assert me.status_code == 200
    assert me.json()["role"] == "admin"


@pytest.mark.asyncio
async def test_candidate_blocked_from_admin_profile(client):
    cand = await register_and_login(client, "candidate")
    res = await client.get("/api/admin/profile", headers=auth(cand["token"]))
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_logout_revokes_token(client):
    cand = await register_and_login(client, "candidate")
    out = await client.post("/api/auth/logout", headers=auth(cand["token"]))
    assert out.status_code == 200
    # Same token must now be rejected.
    res = await client.get(f"/api/settings/{cand['id']}", headers=auth(cand["token"]))
    assert res.status_code == 401


# ── Jobs ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_jobs_crud_and_pagination(client):
    admin = await register_and_login(client, "admin")
    job_id = await make_job(client, admin["token"])

    listed = await client.get("/api/jobs?page=1&limit=10", headers=auth(admin["token"]))
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] >= 1 and body["page"] == 1 and isinstance(body["items"], list)

    upd = await client.put(f"/api/jobs/{job_id}", headers=auth(admin["token"]),
                           json={"title": "Senior Python Engineer"})
    assert upd.status_code == 200 and upd.json()["title"] == "Senior Python Engineer"

    dele = await client.delete(f"/api/jobs/{job_id}", headers=auth(admin["token"]))
    assert dele.status_code == 200


@pytest.mark.asyncio
async def test_candidate_cannot_create_job(client):
    cand = await register_and_login(client, "candidate")
    res = await client.post("/api/jobs", headers=auth(cand["token"]), json={
        "title": "X", "description": "Some description here", "required_skills": ["python"]})
    assert res.status_code == 403


# ── Candidates (admin) ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_candidates_list_search_get(client):
    admin = await register_and_login(client, "admin")
    cand = await register_and_login(client, "candidate")

    lst = await client.get("/api/candidates", headers=auth(admin["token"]))
    assert lst.status_code == 200 and lst.json()["total"] >= 1

    srch = await client.get(f"/api/candidates/search?q={cand['email'][:6]}", headers=auth(admin["token"]))
    assert srch.status_code == 200

    detail = await client.get(f"/api/candidates/{cand['id']}", headers=auth(admin["token"]))
    assert detail.status_code == 200 and detail.json()["id"] == cand["id"]


# ── Profile & settings ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_profile_lifecycle_and_ownership(client):
    cand = await register_and_login(client, "candidate")
    other = await register_and_login(client, "candidate")

    created = await client.post("/api/profile", headers=auth(cand["token"]),
                                json={"user_id": cand["id"], "title": "Engineer", "phone": "123"})
    assert created.status_code == 201

    got = await client.get(f"/api/profile/{cand['id']}", headers=auth(cand["token"]))
    assert got.status_code == 200 and got.json()["title"] == "Engineer"

    # Cross-user access denied.
    denied = await client.get(f"/api/profile/{cand['id']}", headers=auth(other["token"]))
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_settings_default_and_update(client):
    cand = await register_and_login(client, "candidate")
    got = await client.get(f"/api/settings/{cand['id']}", headers=auth(cand["token"]))
    assert got.status_code == 200 and "preferences" in got.json()

    upd = await client.put(f"/api/settings/{cand['id']}", headers=auth(cand["token"]),
                           json={"preferences": {"theme": "dark"}})
    assert upd.status_code == 200 and upd.json()["preferences"]["theme"] == "dark"


# ── Applications ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_application_apply_list_duplicate_withdraw(client):
    admin = await register_and_login(client, "admin")
    cand = await register_and_login(client, "candidate")
    job_id = await make_job(client, admin["token"])

    applied = await client.post("/api/applications/apply", headers=auth(cand["token"]),
                                json={"user_id": cand["id"], "job_id": job_id})
    assert applied.status_code == 201
    app_id = applied.json()["id"]

    dup = await client.post("/api/applications/apply", headers=auth(cand["token"]),
                            json={"user_id": cand["id"], "job_id": job_id})
    assert dup.status_code == 409

    lst = await client.get(f"/api/applications/{cand['id']}", headers=auth(cand["token"]))
    assert lst.status_code == 200 and len(lst.json()) == 1

    wd = await client.delete(f"/api/applications/{app_id}", headers=auth(cand["token"]))
    assert wd.status_code == 200


# ── Mock interview ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mock_interview_flow(client):
    cand = await register_and_login(client, "candidate")
    start = await client.post("/api/mock-interview/start", headers=auth(cand["token"]),
                              json={"role": "Backend", "skills": ["python"]})
    assert start.status_code == 201
    mid = start.json()["mock_interview_id"]

    sub = await client.post("/api/mock-interview/submit", headers=auth(cand["token"]),
                            json={"mock_interview_id": mid, "answer": "I built APIs with FastAPI."})
    assert sub.status_code == 200
    assert sub.json()["complete"] is True and sub.json()["final_score"] is not None

    q = await client.get("/api/mock-interview/questions?skills=python,sql&count=3", headers=auth(cand["token"]))
    assert q.status_code == 200 and len(q.json()["questions"]) == 3


# ── Assessment ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assessment_flow(client):
    cand = await register_and_login(client, "candidate")
    start = await client.get("/api/assessment/start?skills=python,sql&count=4", headers=auth(cand["token"]))
    assert start.status_code == 200
    data = start.json()
    aid = data["assessment_id"]
    assert len(data["questions"]) == 4
    assert "answer_index" not in data["questions"][0]  # answer key not leaked

    answers = {q["id"]: 1 for q in data["questions"]}
    sub = await client.post("/api/assessment/submit", headers=auth(cand["token"]),
                            json={"assessment_id": aid, "answers": answers})
    assert sub.status_code == 200 and sub.json()["status"] == "completed"

    result = await client.get(f"/api/assessment/result/{cand['id']}", headers=auth(cand["token"]))
    assert result.status_code == 200 and result.json()["total"] == 4


# ── Resume (candidate) ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resume_upload_get_delete(client):
    cand = await register_and_login(client, "candidate")
    pdf = io.BytesIO(b"%PDF-1.4\nfake resume content with python and fastapi\n%%EOF")
    up = await client.post("/api/resume/upload", headers=auth(cand["token"]),
                           files={"file": ("resume.pdf", pdf, "application/pdf")})
    assert up.status_code == 202, up.text
    resume_id = up.json()["resume_id"]

    got = await client.get(f"/api/resume/{cand['id']}", headers=auth(cand["token"]))
    assert got.status_code == 200 and len(got.json()) == 1
    assert got.json()[0]["parse_status"] == "pending"  # parsing runs async in background

    dele = await client.delete(f"/api/resume/{resume_id}", headers=auth(cand["token"]))
    assert dele.status_code == 200


@pytest.mark.asyncio
async def test_resume_upload_rejects_non_pdf(client):
    cand = await register_and_login(client, "candidate")
    txt = io.BytesIO(b"just plain text, not a pdf at all")
    res = await client.post("/api/resume/upload", headers=auth(cand["token"]),
                            files={"file": ("notes.txt", txt, "text/plain")})
    assert res.status_code == 415


# ── AI endpoints ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_skill_analysis_owner_only(client):
    cand = await register_and_login(client, "candidate")
    res = await client.get(f"/api/ai/skill-analysis/{cand['id']}", headers=auth(cand["token"]))
    assert res.status_code == 200
    assert "strengths" in res.json() and "gaps" in res.json()


@pytest.mark.asyncio
async def test_ai_recommendations_admin(client):
    admin = await register_and_login(client, "admin")
    res = await client.get("/api/ai/recommendations", headers=auth(admin["token"]))
    assert res.status_code == 200 and isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_job_recommendations_and_search(client):
    admin = await register_and_login(client, "admin")
    cand = await register_and_login(client, "candidate")
    await make_job(client, admin["token"])

    recs = await client.get(f"/api/jobs/recommendations/{cand['id']}", headers=auth(cand["token"]))
    assert recs.status_code == 200 and isinstance(recs.json(), list)

    srch = await client.get("/api/search/jobs?query=python", headers=auth(cand["token"]))
    assert srch.status_code == 200 and srch.json()["total"] >= 1


# ── Dashboard & analytics (admin) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dashboard_and_analytics(client):
    admin = await register_and_login(client, "admin")
    cand = await register_and_login(client, "candidate")
    job_id = await make_job(client, admin["token"])
    await client.post("/api/applications/apply", headers=auth(cand["token"]),
                      json={"user_id": cand["id"], "job_id": job_id})

    summary = await client.get("/api/dashboard/summary", headers=auth(admin["token"]))
    assert summary.status_code == 200
    s = summary.json()
    assert s["total_jobs"] >= 1 and s["total_applications"] >= 1

    for path in ("/api/dashboard/activity", "/api/dashboard/progress",
                 "/api/analytics/skills", "/api/analytics/status",
                 "/api/analytics/match-scores", "/api/analytics/interview-performance"):
        r = await client.get(path, headers=auth(admin["token"]))
        assert r.status_code == 200, f"{path} -> {r.status_code}"

    # Candidate is blocked from admin analytics.
    blocked = await client.get("/api/analytics/skills", headers=auth(cand["token"]))
    assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_match_results_after_apply(client):
    admin = await register_and_login(client, "admin")
    cand = await register_and_login(client, "candidate")
    job_id = await make_job(client, admin["token"])
    await client.post("/api/applications/apply", headers=auth(cand["token"]),
                      json={"user_id": cand["id"], "job_id": job_id})

    mr = await client.get("/api/match-results", headers=auth(admin["token"]))
    assert mr.status_code == 200 and "items" in mr.json()
