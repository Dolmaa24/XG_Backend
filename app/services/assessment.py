"""
Skill assessment generation and scoring.

Tries the AI microservice (`POST /assessment/generate`) first via ai_client;
falls back to a local multiple-choice question bank so assessments work offline.
Scoring always happens server-side.
"""
import logging
import uuid

from app.services.ai_client import _call

logger = logging.getLogger(__name__)

# Local fallback question bank: skill -> list of {prompt, options, answer_index}
_BANK: dict[str, list[dict]] = {
    "python": [
        {"prompt": "Which keyword defines a function in Python?",
         "options": ["func", "def", "function", "lambda"], "answer_index": 1},
        {"prompt": "What data structure does {} create by default?",
         "options": ["set", "list", "dict", "tuple"], "answer_index": 2},
    ],
    "sql": [
        {"prompt": "Which clause filters rows in a SELECT query?",
         "options": ["ORDER BY", "WHERE", "GROUP BY", "HAVING"], "answer_index": 1},
        {"prompt": "Which statement removes a table entirely?",
         "options": ["DELETE", "TRUNCATE", "DROP", "REMOVE"], "answer_index": 2},
    ],
    "docker": [
        {"prompt": "Which file defines how a Docker image is built?",
         "options": ["docker-compose.yml", "Dockerfile", "image.cfg", "build.json"], "answer_index": 1},
    ],
    "fastapi": [
        {"prompt": "FastAPI request/response validation is powered by which library?",
         "options": ["marshmallow", "pydantic", "cerberus", "voluptuous"], "answer_index": 1},
    ],
    "react": [
        {"prompt": "Which hook adds local state to a function component?",
         "options": ["useEffect", "useState", "useRef", "useMemo"], "answer_index": 1},
    ],
    "aws": [
        {"prompt": "Which AWS service provides object storage?",
         "options": ["EC2", "S3", "RDS", "Lambda"], "answer_index": 1},
    ],
}


def _generic_question(skill: str) -> dict:
    return {
        "prompt": f"Which best describes a strong practice when working with {skill}?",
        "options": [
            f"Avoid documenting {skill} usage",
            f"Follow established {skill} conventions and test thoroughly",
            f"Hardcode all {skill} configuration",
            f"Skip error handling in {skill} code",
        ],
        "answer_index": 1,
    }


def _build_local(skills: list[str], count: int) -> list[dict]:
    skills = skills or ["general"]
    questions: list[dict] = []
    i = 0
    while len(questions) < count and i < count * 3:
        skill = skills[i % len(skills)]
        bank = _BANK.get(skill.lower())
        if bank:
            q = bank[(i // max(1, len(skills))) % len(bank)]
        else:
            q = _generic_question(skill)
        questions.append({
            "id": f"q{len(questions) + 1}",
            "skill": skill,
            "type": "mcq",
            "prompt": q["prompt"],
            "options": q["options"],
            "answer_index": q["answer_index"],
        })
        i += 1
    return questions[:count]


async def generate(skills: list[str], count: int = 10) -> list[dict]:
    """Return a list of question dicts INCLUDING the server-side answer_index."""
    remote = await _call("/assessment/generate", {"skills": skills, "count": count})
    if remote and isinstance(remote.get("questions"), list) and remote["questions"]:
        questions = []
        for n, q in enumerate(remote["questions"], start=1):
            questions.append({
                "id": q.get("id") or f"q{n}",
                "skill": q.get("skill", "general"),
                "type": q.get("type", "mcq"),
                "prompt": q.get("prompt", ""),
                "options": q.get("options", []),
                "answer_index": int(q.get("answer_index", 0)),
            })
        return questions
    return _build_local(skills, count)


def score(questions: list[dict], answers: dict[str, int]) -> tuple[float, int, int]:
    """Return (percentage_score, correct_count, total)."""
    total = len(questions)
    if total == 0:
        return 0.0, 0, 0
    correct = 0
    for q in questions:
        selected = answers.get(q["id"])
        if selected is not None and int(selected) == int(q.get("answer_index", -1)):
            correct += 1
    return round(correct / total * 100, 2), correct, total
