def generate_match_report(
    skill_score: float,
    semantic_score: float,
    experience_score: float,
    education_score: float,
    final_score: float,
) -> dict:
    return {
        "skill_match": skill_score,
        "semantic_match": semantic_score,
        "experience_match": experience_score,
        "education_match": education_score,
        "overall_match": final_score,
    }
