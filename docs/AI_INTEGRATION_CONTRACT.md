# AI Integration Contract

This is the canonical spec for the **AI team's HTTP microservice**. The backend's
`app/services/ai_client.py` calls these endpoints when `AI_SERVICE_ENABLED=true`.
When disabled or on any error/timeout, the backend transparently falls back to its
own local services, so implementing this is a drop-in upgrade — not a blocker.

- Base URL: `AI_SERVICE_URL` (e.g. `http://ai:9000`)
- All endpoints accept and return JSON.
- Score conventions: `resume_score`, `match_score`, `final_score` are **0–100 floats**.
  Interview per-answer `score` is a **0–10 integer**.
- The backend tolerates missing/extra fields, but the keys below should be present.

Maps to the AI team's existing modules in `ai/`: `resume_parser`, `matching_engine`,
`interview_engine`, `ranking_engine`.

---

## `GET /health`
Liveness check.
```json
// 200
{ "status": "ok" }
```

## `POST /match`  → `matching_engine`
```json
// request
{ "candidate_skills": ["python","react"],
  "job_skills": ["python","fastapi","docker"],
  "candidate_text": "...", "job_description": "..." }
// response
{ "match_score": 67.5, "matched_skills": ["python"], "missing_skills": ["fastapi","docker"] }
```
Backend fallback: `app/services/matcher.compute_match_score`.

## `POST /skill-analysis`  → `matching_engine` + `resume_parser`
```json
// request
{ "skills": ["python","sql"], "target_skills": ["python","aws","docker"] }
// response
{ "strengths": ["python"], "gaps": ["aws","docker"],
  "skill_levels": { "python": "advanced", "sql": "intermediate" },
  "recommendations": ["Learn Docker fundamentals"] }
```

## `POST /recommendations/jobs`  → `matching_engine` + `ranking_engine`
```json
// request
{ "candidate_skills": ["python","react"],
  "jobs": [ { "job_id": "uuid", "title": "...", "required_skills": ["..."], "description": "..." } ] }
// response
{ "recommendations": [
    { "job_id": "uuid", "title": "...", "score": 88.0,
      "matched_skills": ["python"], "missing_skills": [], "reasons": ["..."] } ] }
```

## `POST /recommendations/candidates`  → `ranking_engine`
```json
// request
{ "job": { "title": "...", "required_skills": ["..."], "description": "..." },
  "candidates": [ { "user_id": "uuid", "name": "...", "skills": ["..."],
                    "resume_score": 80, "match_score": 70, "interview_score": 75 } ] }
// response
{ "recommendations": [ { "user_id": "uuid", "name": "...", "final_score": 76.5, "summary": "..." } ] }
```

## `POST /interview/turn`  → `interview_engine`  (needs a real LLM)
Single endpoint used for both generating a question and evaluating an answer.
```json
// request — first turn (no answer yet)
{ "job_title": "Backend Engineer", "required_skills": ["python","fastapi"],
  "candidate_profile": { "skills": ["..."], "experience": ["..."] },
  "conversation": [], "latest_answer": null }
// response — a question
{ "type": "question", "question": "Walk me through ...", "category": "technical" }

// request — evaluating an answer
{ "...": "same context", "conversation": [ { "question": "...", "answer": null } ],
  "latest_answer": "my answer" }
// response — evaluation + next question
{ "type": "evaluation", "score": 8, "feedback": "Clear and correct ...",
  "next_question": "Now describe ...", "complete": false }
```
Rules: `score` is 0–10; on the final turn set `next_question: null` and `complete: true`;
return valid JSON only; sanitize candidate input against prompt injection.
Backend fallback: `app/services/interviewer` (LLM) → heuristic template if no LLM key.

## `POST /assessment/generate`  → new (interview_engine style)
```json
// request
{ "skills": ["python","sql"], "count": 10 }
// response
{ "questions": [
    { "id": "q1", "skill": "python", "type": "mcq",
      "prompt": "What does ... ?", "options": ["a","b","c","d"], "answer_index": 2 } ] }
```
`answer_index` stays server-side; the backend scores submissions. Optionally add
`POST /assessment/score` if the AI team prefers to own scoring.

---

## Handshake / rollout
1. AI team implements the above and exposes `/health`.
2. Provide a `Dockerfile` + listening port; backend adds the service to `docker-compose.yml` on `ai_hr_net`.
3. Backend sets `AI_SERVICE_ENABLED=true` and `AI_SERVICE_URL`, then runs the joint smoke test.
4. Any field mismatch → raise it before building so we adjust the contract early.
