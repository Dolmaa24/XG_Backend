"""Interview evaluation rubric — embedded in LLM system prompts."""

RUBRIC: dict[str, str] = {
    "0-3": "Poor understanding. Incorrect answer with major conceptual gaps.",
    "4-6": "Basic understanding. Partial answer with limited examples.",
    "7-8": "Strong understanding. Relevant practical examples provided.",
    "9-10": "Expert understanding. Deep reasoning and implementation experience.",
}


def format_rubric_for_prompt() -> str:
    """Serialize rubric for inclusion in LLM system prompt."""
    lines = ["Evaluation Rubric (score each answer 0-10):"]
    for band, description in RUBRIC.items():
        lines.append(f"  Score {band}: {description}")
    return "\n".join(lines)
