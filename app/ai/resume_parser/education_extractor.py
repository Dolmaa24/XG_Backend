"""Education keyword extraction — supplements spaCy/regex pipeline."""

EDUCATION_KEYWORDS = [
    "b.tech",
    "bca",
    "mca",
    "mba",
    "m.tech",
    "bachelor",
    "master",
    "phd",
    "diploma",
    "university",
    "college",
    "institute",
    "b.e",
    "m.e",
    "degree",
]


def extract_education(text: str) -> list[dict]:
    """Return structured education entries found via keyword matching."""
    lower = text.lower()
    found: list[dict] = []

    for keyword in EDUCATION_KEYWORDS:
        if keyword in lower:
            found.append({"keyword": keyword, "source": "ai_layer"})

    # Also capture full lines containing education keywords
    for line in text.split("\n"):
        line_lower = line.lower().strip()
        if any(kw in line_lower for kw in EDUCATION_KEYWORDS):
            entry = line.strip()
            if entry and len(entry) > 5:
                found.append({"raw": entry[:300], "source": "ai_layer"})

    # Deduplicate by raw/keyword
    seen: set[str] = set()
    unique: list[dict] = []
    for item in found:
        key = item.get("raw") or item.get("keyword", "")
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique[:5]
