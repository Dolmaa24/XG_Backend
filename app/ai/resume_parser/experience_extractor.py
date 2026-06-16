"""Experience keyword extraction — supplements spaCy/regex pipeline."""

EXPERIENCE_KEYWORDS = [
    "intern",
    "software engineer",
    "developer",
    "data analyst",
    "machine learning engineer",
    "engineer",
    "analyst",
    "manager",
    "lead",
    "architect",
    "consultant",
    "specialist",
]


def extract_experience(text: str) -> list[dict]:
    """Return structured experience entries found via keyword matching."""
    lower = text.lower()
    found: list[dict] = []

    for role in EXPERIENCE_KEYWORDS:
        if role in lower:
            found.append({"role": role, "source": "ai_layer"})

    for line in text.split("\n"):
        line_lower = line.lower().strip()
        if any(kw in line_lower for kw in EXPERIENCE_KEYWORDS):
            entry = line.strip()
            if entry and len(entry) > 5:
                found.append({"raw": entry[:300], "source": "ai_layer"})

    seen: set[str] = set()
    unique: list[dict] = []
    for item in found:
        key = item.get("raw") or item.get("role", "")
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique[:10]
