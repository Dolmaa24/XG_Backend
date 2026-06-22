class CandidateScorer:
    WEIGHTS = {
        "resume": 0.35,
        "technical": 0.30,
        "behavioral": 0.15,
        "communication": 0.10,
        "experience": 0.10,
    }

    @classmethod
    def calculate_score(
        cls,
        resume_score: float,
        technical_score: float,
        behavioral_score: float,
        communication_score: float,
        experience_score: float,
    ) -> float:
        return round(
            resume_score       * cls.WEIGHTS["resume"]
            + technical_score  * cls.WEIGHTS["technical"]
            + behavioral_score * cls.WEIGHTS["behavioral"]
            + communication_score * cls.WEIGHTS["communication"]
            + experience_score * cls.WEIGHTS["experience"],
            2,
        )
