import json
import logging
import re
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── All hardcoded values pulled from config ──────────────────────────────────
# REFACTOR [MEDIUM]: MAX_QUESTIONS was hardcoded as literal 5 — now from settings
MAX_QUESTIONS = settings.MAX_INTERVIEW_QUESTIONS
LLM_MAX_TOKENS = settings.LLM_MAX_TOKENS
ANSWER_MAX_LENGTH = settings.ANSWER_MAX_LENGTH

# SECURITY [HIGH]: expanded injection phrase list + unicode normalization
_INJECTION_PHRASES = [
    "ignore previous", "ignore all", "system:", "assistant:", "you are now",
    "disregard", "forget your instructions", "new instructions", "override",
    "act as", "pretend you are", "jailbreak", "dan mode", "developer mode",
    "ignore the above", "ignore everything", "do not follow",
]


# ── Prompt injection sanitizer ───────────────────────────────────────────────

def _sanitize_input(text: str) -> str:
    """
    SECURITY [HIGH]: Strip prompt injection attempts from candidate answers.
    Uses unicode normalization to catch encoded variants.
    """
    import unicodedata
    # Normalize unicode so encoded lookalikes are caught
    normalized = unicodedata.normalize("NFKC", text)
    lower = normalized.lower()

    for phrase in _INJECTION_PHRASES:
        if phrase in lower:
            logger.warning({"event": "prompt_injection_blocked", "phrase": phrase})
            return "[Candidate answer was filtered due to invalid content]"

    # Strip control characters except newlines and tabs
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", normalized)

    # SECURITY [MEDIUM]: hard cap prevents token flooding
    return cleaned[:ANSWER_MAX_LENGTH]


# ── LLM client factory ───────────────────────────────────────────────────────

def _get_llm_response(messages: list[dict], system: str) -> str:
    if settings.LLM_PROVIDER == "anthropic":
        return _call_anthropic(messages, system)
    return _call_openai(messages, system)


def _call_anthropic(messages: list[dict], system: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=LLM_MAX_TOKENS,
        system=system,
        messages=messages,
    )
    return response.content[0].text


def _call_openai(messages: list[dict], system: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    full_messages = [{"role": "system", "content": system}] + messages
    response = client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=full_messages,
        max_tokens=LLM_MAX_TOKENS,
        temperature=0.7,
    )
    return response.choices[0].message.content


# ── JSON extraction ───────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict:
    """
    REFACTOR [MEDIUM]: Robust JSON extraction.
    Handles LLM responses that wrap JSON in markdown fences.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try extracting first {...} block
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    logger.warning({"event": "llm_json_parse_failed", "raw_preview": raw[:200]})
    return {}


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_system_prompt(
    job_title: str,
    required_skills: list[str],
    candidate_profile: dict,
) -> str:
    # SECURITY [HIGH]: sanitize job/profile data before embedding in system prompt
    # HR-created job titles and candidate data go into the system prompt —
    # a malicious HR user could inject instructions here
    safe_title = _sanitize_input(job_title)[:200]
    skills_str = ", ".join(str(s)[:50] for s in required_skills[:30])
    candidate_skills = ", ".join(
        str(s)[:50] for s in candidate_profile.get("skills", [])[:30]
    ) or "not specified"
    experience = candidate_profile.get("experience", [])
    exp_summary = "; ".join(
        [str(e.get("raw", ""))[:100] for e in experience[:3]]
    ) or "not specified"

    return f"""You are a professional technical interviewer conducting a structured job interview.

Job Title: {safe_title}
Required Skills: {skills_str}
Candidate Skills: {candidate_skills}
Candidate Experience: {exp_summary}

Rules:
1. Ask relevant technical and behavioural questions based on the job requirements.
2. Vary between technical, situational, and behavioural question types.
3. Never repeat a question already asked in this conversation.
4. Keep questions concise and clear.

CRITICAL: Respond ONLY with valid JSON. No prose, no markdown fences, no text outside JSON.

To generate a question:
{{"type": "question", "question": "<your question>", "category": "technical|behavioural|situational"}}

To evaluate an answer:
{{"type": "evaluation", "score": <integer 0-10>, "feedback": "<brief feedback>", "next_question": "<next question string or null>"}}"""


# ── Public API ────────────────────────────────────────────────────────────────

def generate_first_question(
    job_title: str,
    required_skills: list[str],
    candidate_profile: dict,
) -> dict:
    """Generate the opening interview question."""
    system = _build_system_prompt(job_title, required_skills, candidate_profile)
    messages = [{"role": "user", "content": "Begin the interview. Ask your first question."}]

    raw = _get_llm_response(messages, system)
    result = _extract_json(raw)

    question = result.get("question") or "Tell me about yourself and your relevant experience for this role."
    category = result.get("category", "general")

    logger.info({"event": "first_question_generated", "job_title": job_title})
    return {"question": question, "category": category}


def evaluate_answer_and_next(
    job_title: str,
    required_skills: list[str],
    candidate_profile: dict,
    conversation: list[dict],
    latest_answer: str,
) -> dict:
    """
    Evaluate the candidate's latest answer and generate the next question.
    Returns: {answer_score, feedback, next_question, interview_complete}
    """
    system = _build_system_prompt(job_title, required_skills, candidate_profile)

    # Build conversation history — sanitize every candidate answer
    messages = []
    for turn in conversation:
        if turn.get("question"):
            messages.append({"role": "assistant", "content": str(turn["question"])})
        if turn.get("answer"):
            messages.append({"role": "user", "content": _sanitize_input(str(turn["answer"]))})

    messages.append({"role": "user", "content": _sanitize_input(latest_answer)})

    question_count = sum(1 for t in conversation if t.get("question"))
    is_last = question_count >= MAX_QUESTIONS

    instruction = (
        "This is the final answer. Evaluate it and set next_question to null."
        if is_last
        else "Evaluate this answer and provide the next interview question."
    )
    messages.append({"role": "user", "content": instruction})

    raw = _get_llm_response(messages, system)
    result = _extract_json(raw)

    try:
        raw_score = float(result.get("score", 5))
        # Clamp to 0-10 before normalizing
        raw_score = max(0.0, min(10.0, raw_score))
        answer_score = round(raw_score / 10 * 100, 2)
        feedback = str(result.get("feedback", "Your answer has been recorded."))[:500]
        next_question = result.get("next_question")
        if is_last:
            next_question = None
    except (ValueError, TypeError):
        logger.warning({"event": "eval_score_parse_failed", "raw_preview": raw[:200]})
        answer_score = 50.0
        feedback = "Your answer has been recorded."
        next_question = None if is_last else "Can you walk me through a challenging technical project?"

    # EDGE CASE: LLM may return empty string for next_question — treat as None
    if next_question is not None and not str(next_question).strip():
        next_question = None

    interview_complete = is_last or next_question is None

    logger.info({
        "event": "answer_evaluated",
        "answer_score": answer_score,
        "interview_complete": interview_complete,
        "question_number": question_count,
    })

    return {
        "answer_score": answer_score,
        "feedback": feedback,
        "next_question": next_question,
        "interview_complete": interview_complete,
    }


def compute_final_interview_score(conversation: list[dict]) -> float:
    """Average all per-answer scores from conversation history."""
    scores = [
        float(t["answer_score"])
        for t in conversation
        if t.get("answer_score") is not None
    ]
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 2)


def generate_candidate_summary(
    candidate_name: str,
    job_title: str,
    resume_score: float,
    match_score: float,
    interview_score: float,
    final_score: float,
) -> str:
    """Generate a 2-sentence HR-facing summary for a candidate."""
    # SECURITY [LOW]: sanitize name and title before embedding in prompt
    safe_name = _sanitize_input(candidate_name)[:100]
    safe_title = _sanitize_input(job_title)[:100]

    system = (
        "You are an HR assistant. Write exactly 2 concise sentences summarising a candidate "
        "for a hiring manager. Be objective and factual. No markdown. No bullet points."
    )
    prompt = (
        f"Candidate: {safe_name}\n"
        f"Applied for: {safe_title}\n"
        f"Resume Score: {resume_score}/100\n"
        f"Job Match Score: {match_score}/100\n"
        f"Interview Score: {interview_score}/100\n"
        f"Final Score: {final_score}/100\n"
        "Write a 2-sentence summary for the hiring manager."
    )
    try:
        summary = _get_llm_response([{"role": "user", "content": prompt}], system)
        return summary.strip()[:500]
    except Exception as e:
        logger.warning({"event": "summary_generation_failed", "error": str(e)})
        return f"{safe_name} scored {final_score}/100 overall for the {safe_title} role."
