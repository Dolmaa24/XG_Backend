import uuid
from datetime import datetime
from typing import Optional, Any, Generic, TypeVar
from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="candidate", pattern="^(candidate|hr|admin)$")


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


# ── Generic helpers ───────────────────────────────────────────────────────────

T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    limit: int


class MessageResponse(BaseModel):
    message: str


# ── Auth (frontend contract) ───────────────────────────────────────────────────

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# ── Profile ─────────────────────────────────────────────────────────────────

class ProfileBase(BaseModel):
    full_name: Optional[str] = Field(None, max_length=120)
    title: Optional[str] = Field(None, max_length=160)
    phone: Optional[str] = Field(None, max_length=40)
    location: Optional[str] = Field(None, max_length=160)
    bio: Optional[str] = None
    social_links: dict[str, str] = {}


class ProfileCreate(ProfileBase):
    user_id: uuid.UUID


class ProfileUpdate(ProfileBase):
    pass


class ProfileOut(ProfileBase):
    id: uuid.UUID
    user_id: uuid.UUID
    avatar_url: Optional[str] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class AvatarUploadResponse(BaseModel):
    user_id: uuid.UUID
    avatar_url: str


# ── Candidates (admin) ─────────────────────────────────────────────────────────

class CandidateSummary(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: str
    created_at: datetime
    resume_count: int = 0
    application_count: int = 0

    model_config = {"from_attributes": True}


class CandidateDetail(CandidateSummary):
    skills: list[str] = []
    latest_resume_id: Optional[uuid.UUID] = None
    latest_resume_score: Optional[float] = None


# ── Jobs (frontend contract additions) ─────────────────────────────────────────

class JobUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = Field(None, min_length=10)
    required_skills: Optional[list[str]] = None
    experience_years: Optional[int] = Field(None, ge=0, le=50)


class JobRecommendation(BaseModel):
    job_id: uuid.UUID
    title: str
    score: float
    matched_skills: list[str] = []
    missing_skills: list[str] = []
    reasons: list[str] = []


# ── Applications ────────────────────────────────────────────────────────────

class ApplicationCreate(BaseModel):
    user_id: uuid.UUID
    job_id: uuid.UUID
    cover_note: Optional[str] = Field(None, max_length=2000)


class ApplicationOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    job_id: uuid.UUID
    job_title: Optional[str] = None
    status: str
    cover_note: Optional[str] = None
    applied_at: datetime

    model_config = {"from_attributes": True}


# ── Settings ─────────────────────────────────────────────────────────────────

class SettingsUpdate(BaseModel):
    preferences: dict[str, Any]


class SettingsOut(BaseModel):
    user_id: uuid.UUID
    preferences: dict[str, Any]
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── AI: skill analysis & recommendations ────────────────────────────────────

class SkillAnalysisResponse(BaseModel):
    user_id: uuid.UUID
    strengths: list[str] = []
    gaps: list[str] = []
    skill_levels: dict[str, str] = {}
    recommendations: list[str] = []


class CandidateRecommendation(BaseModel):
    user_id: uuid.UUID
    name: str
    final_score: float
    summary: Optional[str] = None


# ── Mock interview ────────────────────────────────────────────────────────────

class MockInterviewStartRequest(BaseModel):
    role: Optional[str] = Field(None, max_length=160)
    skills: list[str] = Field(default_factory=list)


class MockInterviewStartResponse(BaseModel):
    mock_interview_id: uuid.UUID
    first_question: str


class MockInterviewSubmitRequest(BaseModel):
    mock_interview_id: uuid.UUID
    answer: str = Field(..., min_length=1, max_length=4000)


class MockInterviewSubmitResponse(BaseModel):
    next_question: Optional[str]
    answer_score: float
    feedback: str
    complete: bool
    final_score: Optional[float] = None


class MockQuestionsResponse(BaseModel):
    questions: list[str]


# ── Skill assessment ──────────────────────────────────────────────────────────

class AssessmentQuestion(BaseModel):
    id: str
    skill: str
    type: str = "mcq"
    prompt: str
    options: list[str] = []


class AssessmentStartResponse(BaseModel):
    assessment_id: uuid.UUID
    questions: list[AssessmentQuestion]


class AssessmentSubmitRequest(BaseModel):
    assessment_id: uuid.UUID
    answers: dict[str, int]   # {question_id: selected_option_index}


class AssessmentResultResponse(BaseModel):
    assessment_id: uuid.UUID
    user_id: uuid.UUID
    score: Optional[float]
    status: str
    correct: int = 0
    total: int = 0
    completed_at: Optional[datetime] = None


# ── Interviews (read views) ────────────────────────────────────────────────────

class InterviewResultOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    job_id: Optional[uuid.UUID] = None
    candidate_name: Optional[str] = None
    job_title: Optional[str] = None          # for mock interviews this is the target role
    interview_score: Optional[float] = None
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Match results (admin) ──────────────────────────────────────────────────────

class MatchResultOut(BaseModel):
    user_id: uuid.UUID
    candidate_name: str
    job_id: uuid.UUID
    job_title: str
    resume_score: float
    match_score: float
    interview_score: float
    final_score: float
    status: str
    recommendation: str


# ── Dashboard & analytics ──────────────────────────────────────────────────────

class DashboardSummary(BaseModel):
    total_candidates: int
    total_jobs: int
    total_applications: int
    total_interviews: int
    completed_interviews: int
    avg_match_score: float
    avg_interview_score: float


class ActivityItem(BaseModel):
    type: str
    description: str
    timestamp: datetime


class ProgressStage(BaseModel):
    stage: str
    count: int


class CountItem(BaseModel):
    label: str
    count: int


class DistributionBucket(BaseModel):
    bucket: str
    count: int
