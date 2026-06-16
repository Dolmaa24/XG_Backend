"""Prompt templates for the interview LLM."""

from app.ai.interview_engine.interview_config import QUESTION_TYPES
from app.ai.interview_engine.rubric import format_rubric_for_prompt

INTERVIEW_OBJECTIVES = [
    "Assess technical skills",
    "Assess problem solving",
    "Assess communication",
]

INTERVIEW_RULES = [
    "Ask one question at a time",
    "Avoid repetition",
    "Return JSON only",
    f"Vary question types among: {', '.join(QUESTION_TYPES)}",
]


def build_interview_prompt_header() -> str:
    """Base prompt header from XTRAGRAD-AI prompt_template.md."""
    objectives = "\n".join(f"- {o}" for o in INTERVIEW_OBJECTIVES)
    rules = "\n".join(f"- {r}" for r in INTERVIEW_RULES)
    return (
        "You are a senior technical interviewer.\n\n"
        f"Objectives:\n{objectives}\n\n"
        f"Rules:\n{rules}"
    )


def build_full_system_prompt(
    job_title: str,
    required_skills: str,
    candidate_skills: str,
    experience_summary: str,
) -> str:
    """Compose complete system prompt with rubric and job context."""
    header = build_interview_prompt_header()
    rubric = format_rubric_for_prompt()
    return f"""{header}

{rubric}

Job Title: {job_title}
Required Skills: {required_skills}
Candidate Skills: {candidate_skills}
Candidate Experience: {experience_summary}

CRITICAL: Respond ONLY with valid JSON. No prose, no markdown fences.

To generate a question:
{{"type": "question", "question": "<your question>", "category": "technical|behavioural|situational"}}

To evaluate an answer:
{{"type": "evaluation", "score": <integer 0-10>, "feedback": "<brief feedback>", "next_question": "<next question or null>"}}"""
