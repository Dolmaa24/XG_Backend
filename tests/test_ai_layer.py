"""
AI layer integration tests — validates modules from XTRAGRAD-AI commit e0bf2eb.
Run: pytest tests/test_ai_layer.py -v
"""
import pytest

from app.ai.config.settings import get_ai_settings
from app.ai.matching_engine.job_matcher import calculate_match_score
from app.ai.matching_engine.skill_matcher import skill_match_score
from app.ai.interview_engine.rubric import RUBRIC, format_rubric_for_prompt
from app.ai.interview_engine.interview_config import MAX_QUESTIONS, QUESTION_TYPES
from app.ai.ranking_engine.weights import compute_weighted_score, DEFAULT_WEIGHTS
from app.ai.resume_parser.education_extractor import extract_education
from app.ai.resume_parser.experience_extractor import extract_experience
from app.ai.prompts import build_interview_prompt_header, build_full_system_prompt


class TestAIConfig:
    def test_settings_load_from_backend(self):
        cfg = get_ai_settings()
        assert cfg.SKILL_MATCH_THRESHOLD == 0.75
        assert cfg.SKILL_SCORE_WEIGHT == 0.70
        assert cfg.DOC_SCORE_WEIGHT == 0.30
        assert cfg.MAX_INTERVIEW_QUESTIONS == 5


class TestMatchingEngine:
    def test_skill_match_full_overlap(self):
        score = skill_match_score(["python", "fastapi"], ["python", "fastapi"])
        assert score == 1.0

    def test_skill_match_partial_overlap(self):
        score = skill_match_score(["python"], ["python", "fastapi", "postgresql"])
        assert abs(score - 1 / 3) < 0.01

    def test_skill_match_empty_job(self):
        assert skill_match_score(["python"], []) == 0.0

    def test_job_matcher_blend(self):
        result = calculate_match_score(80.0, 60.0)
        assert result == round(80 * 0.7 + 60 * 0.3, 2)

    def test_job_matcher_caps_at_100(self):
        result = calculate_match_score(100.0, 100.0)
        assert result == 100.0


class TestInterviewEngine:
    def test_rubric_has_four_bands(self):
        assert len(RUBRIC) == 4

    def test_rubric_formats_for_prompt(self):
        text = format_rubric_for_prompt()
        assert "Score 0-3" in text
        assert "Score 9-10" in text

    def test_interview_config(self):
        assert MAX_QUESTIONS == 5
        assert "technical" in QUESTION_TYPES
        assert "behavioral" in QUESTION_TYPES

    def test_prompt_header_contains_objectives(self):
        header = build_interview_prompt_header()
        assert "senior technical interviewer" in header
        assert "JSON only" in header

    def test_full_system_prompt_includes_job_context(self):
        prompt = build_full_system_prompt(
            job_title="Backend Engineer",
            required_skills="python, fastapi",
            candidate_skills="python, django",
            experience_summary="2 years backend dev",
        )
        assert "Backend Engineer" in prompt
        assert "Evaluation Rubric" in prompt


class TestRankingEngine:
    def test_default_weights_sum_to_one(self):
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_compute_weighted_score(self):
        score = compute_weighted_score(80, 70, 90)
        expected = round(80 * 0.30 + 70 * 0.30 + 90 * 0.40, 2)
        assert score == expected

    def test_custom_weights(self):
        score = compute_weighted_score(
            100, 0, 0,
            weights={"resume": 1.0, "match": 0.0, "interview": 0.0},
        )
        assert score == 100.0


class TestResumeParser:
    def test_extract_education_finds_degree(self):
        text = "Bachelor of Technology in Computer Science from MIT"
        result = extract_education(text)
        assert len(result) > 0

    def test_extract_experience_finds_role(self):
        text = "Software Engineer at Acme Corp for 3 years"
        result = extract_experience(text)
        assert len(result) > 0
        assert any("software engineer" in str(r).lower() for r in result)

    def test_extract_education_empty_text(self):
        assert extract_education("") == []


class TestServiceIntegration:
    """Verify services delegate to AI layer correctly."""

    def test_matcher_uses_ai_blend(self):
        from unittest.mock import patch, MagicMock
        import numpy as np
        from app.services.matcher import compute_match_score

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([
            [1.0, 0.0], [0.0, 1.0], [1.0, 0.0], [0.0, 1.0],
        ])

        with patch("app.services.matcher.load_embedding_model", return_value=mock_model):
            result = compute_match_score(
                candidate_skills=["python"],
                job_skills=["python"],
                candidate_text="Python developer",
                job_description="Python backend role",
            )
        assert "match_score" in result
        assert 0 <= result["match_score"] <= 100

    def test_interviewer_uses_ai_prompt(self):
        from app.services.interviewer import _build_system_prompt
        prompt = _build_system_prompt(
            job_title="Engineer",
            required_skills=["python"],
            candidate_profile={"skills": ["python"], "experience": []},
        )
        assert "Evaluation Rubric" in prompt
        assert "senior technical interviewer" in prompt
