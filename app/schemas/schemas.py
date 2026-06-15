import uuid
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="candidate", pattern="^(candidate|hr)$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Jobs ─────────────────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    description: str = Field(..., min_length=10)
    required_skills: list[str] = Field(..., min_length=1)
    experience_years: int = Field(default=0, ge=0, le=50)
    weight_resume: float = Field(default=0.30, ge=0.0, le=1.0)
    weight_match: float = Field(default=0.30, ge=0.0, le=1.0)
    weight_interview: float = Field(default=0.40, ge=0.0, le=1.0)

    @field_validator("weight_interview")
    @classmethod
    def weights_sum_to_one(cls, v, info):
        wr = info.data.get("weight_resume", 0.30)
        wm = info.data.get("weight_match", 0.30)
        total = round(wr + wm + v, 2)
        if total != 1.0:
            raise ValueError(f"Weights must sum to 1.0, got {total}")
        return v


class JobOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    required_skills: list[str]
    experience_years: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Resume ────────────────────────────────────────────────────────────────────

class ResumeUploadResponse(BaseModel):
    resume_id: uuid.UUID
    parse_status: str
    message: str


class ParsedProfile(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    skills: list[str] = []
    education: list[dict[str, Any]] = []
    experience: list[dict[str, Any]] = []
    certifications: list[str] = []


class ResumeProfileOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    parse_status: str
    resume_score: Optional[float]
    parsed_data: Optional[ParsedProfile]
    uploaded_at: datetime

    model_config = {"from_attributes": True}


# ── Matching ──────────────────────────────────────────────────────────────────

class MatchRequest(BaseModel):
    resume_id: uuid.UUID
    job_id: uuid.UUID


class MatchResponse(BaseModel):
    resume_id: uuid.UUID
    job_id: uuid.UUID
    match_score: float
    matched_skills: list[str]
    missing_skills: list[str]


# ── Interview ─────────────────────────────────────────────────────────────────

class InterviewStartRequest(BaseModel):
    resume_id: uuid.UUID
    job_id: uuid.UUID


class InterviewStartResponse(BaseModel):
    interview_id: uuid.UUID
    first_question: str
    job_title: str


class InterviewRespondRequest(BaseModel):
    interview_id: uuid.UUID
    answer: str = Field(..., min_length=1, max_length=4000)


class InterviewRespondResponse(BaseModel):
    next_question: Optional[str]
    answer_score: float
    feedback: str
    interview_complete: bool
    final_interview_score: Optional[float] = None


# ── Ranking ───────────────────────────────────────────────────────────────────

class CandidateRank(BaseModel):
    rank: int
    user_id: uuid.UUID
    name: str
    email: str
    resume_score: float
    match_score: float
    interview_score: float
    final_score: float
    summary: Optional[str]
    status: str


class RankingResponse(BaseModel):
    job_id: uuid.UUID
    job_title: str
    total_candidates: int
    candidates: list[CandidateRank]


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    db: str
    redis: str
    version: str = "1.0.0"


# ── Error ─────────────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    detail: str
