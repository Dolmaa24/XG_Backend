def recommendation(score: float) -> str:
    if score >= 85:
        return "Strongly Recommended"
    if score >= 70:
        return "Recommended"
    return "Not Recommended"
