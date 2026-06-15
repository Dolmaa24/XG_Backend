# AI HR Recruitment Simulator — AI Layer

Integrated from [XTRAGRAD-AI commit e0bf2eb](https://github.com/XTRAGRAD-AI/AI-HR-Recruitment-Simulator/commit/e0bf2ebf297dcc00390d06f886de9f6e226ef963).

## Overview

The AI layer automates resume processing, semantic job matching, AI-driven interviews, and candidate ranking. It is wired into `app/services/` and shares configuration via `app/core/config.py`.

## Modules

| Module | Path | Used by |
|--------|------|---------|
| Resume Parsing | `resume_parser/` | `app/services/parser.py` |
| Semantic Matching | `matching_engine/` | `app/services/matcher.py` |
| Interview Engine | `interview_engine/`, `prompts.py` | `app/services/interviewer.py` |
| Candidate Ranking | `ranking_engine/` | `app/services/ranker.py` |
| Configuration | `config/settings.py` | All AI modules |

## AI Documentation

- [Prompt Design](docs/prompt_template.md)
- [Evaluation Rubric](docs/interview_rubric.md)
- [Matching Strategy](docs/semantic_matching.md)
- [Model Recommendations](docs/ai_improvements.md)

## Development Status

Phase 1 Implementation Complete — integrated with FastAPI backend.
