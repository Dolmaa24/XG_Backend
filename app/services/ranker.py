import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Ranking, User, Job
from app.services.interviewer import generate_candidate_summary

logger = logging.getLogger(__name__)


async def compute_and_store_ranking(
    db: AsyncSession,
    user_id: UUID,
    job_id: UUID,
    resume_score: float,
    match_score: float,
    interview_score: float,
) -> Ranking:
    """Compute weighted final score and upsert ranking row."""
    job = await db.get(Job, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    # PERF [MEDIUM]: weights come from the job row — no separate query needed
    final_score = round(
        resume_score   * job.weight_resume
        + match_score  * job.weight_match
        + interview_score * job.weight_interview,
        2,
    )

    # Upsert — avoid duplicate rows per (user, job) pair
    result = await db.execute(
        select(Ranking).where(
            Ranking.user_id == user_id,
            Ranking.job_id == job_id,
        )
    )
    ranking = result.scalar_one_or_none()

    if ranking:
        ranking.resume_score    = resume_score
        ranking.match_score     = match_score
        ranking.interview_score = interview_score
        ranking.final_score     = final_score
        # Invalidate stale summary so it regenerates on next ranking fetch
        ranking.summary = None
    else:
        ranking = Ranking(
            user_id=user_id,
            job_id=job_id,
            resume_score=resume_score,
            match_score=match_score,
            interview_score=interview_score,
            final_score=final_score,
        )
        db.add(ranking)

    await db.flush()

    logger.info({
        "event": "ranking_updated",
        "user_id": str(user_id),
        "job_id": str(job_id),
        "final_score": final_score,
    })
    return ranking


async def get_ranked_candidates(db: AsyncSession, job_id: UUID) -> dict:
    """
    Fetch all rankings for a job, sorted descending by final_score.
    Generates LLM summaries for any candidate missing one.

    PERF [HIGH]: single JOIN query eliminates N+1 — no per-candidate user lookup.
    EDGE CASE: returns empty list when no candidates have applied.
    """
    job = await db.get(Job, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    # PERF [HIGH]: single query joins rankings + users, ordered server-side
    result = await db.execute(
        select(Ranking, User)
        .join(User, Ranking.user_id == User.id)
        .where(Ranking.job_id == job_id)
        .order_by(Ranking.final_score.desc())
    )
    rows = result.all()

    # EDGE CASE: no candidates have applied / completed pipeline for this job
    if not rows:
        logger.info({"event": "ranking_empty", "job_id": str(job_id)})
        return {
            "job_id": job_id,
            "job_title": job.title,
            "total_candidates": 0,
            "candidates": [],
        }

    candidates = []
    summaries_generated = 0

    for rank_pos, (ranking, user) in enumerate(rows, start=1):
        # Generate and persist summary only when missing or stale
        if not ranking.summary:
            try:
                ranking.summary = generate_candidate_summary(
                    candidate_name=user.name,
                    job_title=job.title,
                    resume_score=ranking.resume_score,
                    match_score=ranking.match_score,
                    interview_score=ranking.interview_score,
                    final_score=ranking.final_score,
                )
                summaries_generated += 1
            except Exception as e:
                # EDGE CASE: LLM unavailable — use fallback summary, don't crash
                logger.warning({"event": "summary_fallback", "user_id": str(user.id), "error": str(e)})
                ranking.summary = f"Candidate scored {ranking.final_score}/100 for {job.title}."

        candidates.append({
            "rank":             rank_pos,
            "user_id":          user.id,
            "name":             user.name,
            "email":            user.email,
            "resume_score":     ranking.resume_score,
            "match_score":      ranking.match_score,
            "interview_score":  ranking.interview_score,
            "final_score":      ranking.final_score,
            "summary":          ranking.summary,
            "status":           ranking.status.value,
        })

    # Batch flush all summary updates in one transaction
    if summaries_generated:
        await db.flush()

    logger.info({
        "event": "ranking_fetched",
        "job_id": str(job_id),
        "count": len(candidates),
        "summaries_generated": summaries_generated,
    })

    return {
        "job_id":            job_id,
        "job_title":         job.title,
        "total_candidates":  len(candidates),
        "candidates":        candidates,
    }
