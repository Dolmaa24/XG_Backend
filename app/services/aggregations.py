"""
Read-side aggregation queries powering the Admin dashboard, analytics, and
match-results endpoints.
"""
import logging
from collections import Counter

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    User, Job, Resume, MockInterview, Ranking, Application, UserRole, ApplicationStatus,
)

# In this simulator the interview activity surfaced to admins is the candidate
# mock-interview (the only interview mechanism the frontend drives), so all
# interview metrics below read from the MockInterview table.

logger = logging.getLogger(__name__)

_SCORE_BUCKETS = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)]


def _bucket_label(lo: int, hi: int) -> str:
    return f"{lo}-{hi}"


def _distribute(values: list[float]) -> list[dict]:
    out = []
    for lo, hi in _SCORE_BUCKETS:
        # top bucket is inclusive of 100
        count = sum(1 for v in values if (lo <= v < hi) or (hi == 100 and v == 100))
        out.append({"bucket": _bucket_label(lo, hi), "count": count})
    return out


async def summary(db: AsyncSession) -> dict:
    total_candidates = await db.scalar(
        select(func.count()).select_from(User).where(User.role == UserRole.candidate))
    total_jobs = await db.scalar(select(func.count()).select_from(Job))
    total_applications = await db.scalar(select(func.count()).select_from(Application))
    total_interviews = await db.scalar(select(func.count()).select_from(MockInterview))
    completed_interviews = await db.scalar(
        select(func.count()).select_from(MockInterview).where(MockInterview.status == "completed"))
    avg_match = await db.scalar(select(func.avg(Ranking.match_score)))
    avg_interview = await db.scalar(
        select(func.avg(MockInterview.score)).where(MockInterview.score.isnot(None)))

    return {
        "total_candidates": total_candidates or 0,
        "total_jobs": total_jobs or 0,
        "total_applications": total_applications or 0,
        "total_interviews": total_interviews or 0,
        "completed_interviews": completed_interviews or 0,
        "avg_match_score": round(float(avg_match or 0.0), 2),
        "avg_interview_score": round(float(avg_interview or 0.0), 2),
    }


async def activity(db: AsyncSession, limit: int = 20) -> list[dict]:
    items: list[dict] = []

    apps = (await db.execute(
        select(Application, User, Job)
        .join(User, Application.user_id == User.id)
        .join(Job, Application.job_id == Job.id)
        .order_by(Application.applied_at.desc()).limit(limit)
    )).all()
    for app, user, job in apps:
        items.append({"type": "application",
                      "description": f"{user.name} applied for {job.title}",
                      "timestamp": app.applied_at})

    resumes = (await db.execute(
        select(Resume, User).join(User, Resume.user_id == User.id)
        .order_by(Resume.uploaded_at.desc()).limit(limit)
    )).all()
    for resume, user in resumes:
        items.append({"type": "resume",
                      "description": f"{user.name} uploaded a resume ({resume.parse_status})",
                      "timestamp": resume.uploaded_at})

    interviews = (await db.execute(
        select(MockInterview, User).join(User, MockInterview.user_id == User.id)
        .order_by(MockInterview.started_at.desc()).limit(limit)
    )).all()
    for itv, user in interviews:
        target = itv.role or "a role"
        items.append({"type": "interview",
                      "description": f"{user.name} {itv.status} a mock interview for {target}",
                      "timestamp": itv.started_at})

    items.sort(key=lambda x: x["timestamp"], reverse=True)
    return items[:limit]


async def _status_counts(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(
        select(Application.status, func.count()).group_by(Application.status)
    )).all()
    counts = {status.value: 0 for status in ApplicationStatus}
    for status_val, cnt in rows:
        key = status_val.value if hasattr(status_val, "value") else str(status_val)
        counts[key] = cnt
    return counts


async def progress(db: AsyncSession) -> list[dict]:
    counts = await _status_counts(db)
    order = ["applied", "screened", "interviewed", "ranked", "rejected"]
    return [{"stage": s, "count": counts.get(s, 0)} for s in order]


async def analytics_skills(db: AsyncSession, limit: int = 15) -> list[dict]:
    rows = (await db.execute(select(Resume.parsed_data).where(Resume.parsed_data.isnot(None)))).all()
    counter: Counter = Counter()
    for (parsed,) in rows:
        if isinstance(parsed, dict):
            for skill in parsed.get("skills", []) or []:
                counter[str(skill).lower()] += 1
    return [{"label": skill, "count": cnt} for skill, cnt in counter.most_common(limit)]


async def analytics_status(db: AsyncSession) -> list[dict]:
    counts = await _status_counts(db)
    return [{"label": k, "count": v} for k, v in counts.items()]


async def analytics_match_scores(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(select(Ranking.match_score))).all()
    values = [float(r[0]) for r in rows if r[0] is not None]
    return _distribute(values)


async def analytics_interview_performance(db: AsyncSession) -> dict:
    rows = (await db.execute(
        select(MockInterview.score).where(MockInterview.score.isnot(None)))).all()
    values = [float(r[0]) for r in rows]
    avg = round(sum(values) / len(values), 2) if values else 0.0
    return {"average": avg, "distribution": _distribute(values)}


async def match_results(db: AsyncSession, page: int, limit: int) -> tuple[list[dict], int]:
    total = await db.scalar(select(func.count()).select_from(Ranking)) or 0
    rows = (await db.execute(
        select(Ranking, User, Job)
        .join(User, Ranking.user_id == User.id)
        .join(Job, Ranking.job_id == Job.id)
        .order_by(Ranking.final_score.desc())
        .offset((page - 1) * limit).limit(limit)
    )).all()
    items = [{
        "user_id": user.id,
        "candidate_name": user.name,
        "job_id": job.id,
        "job_title": job.title,
        "resume_score": ranking.resume_score,
        "match_score": ranking.match_score,
        "interview_score": ranking.interview_score,
        "final_score": ranking.final_score,
        "status": ranking.status.value,
    } for ranking, user, job in rows]
    return items, total
