import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, ForeignKey, Text, DateTime, Enum as SAEnum, Uuid, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB as _PG_JSONB
import enum

from app.core.database import Base

# Portable column types: native UUID + JSONB on PostgreSQL, generic equivalents
# elsewhere (e.g. SQLite for tests). Behaviour on Postgres is unchanged.
UUID = Uuid                                  # Uuid(as_uuid=True) -> native uuid on PG
JSONB = JSON().with_variant(_PG_JSONB(), "postgresql")


def utcnow():
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    candidate = "candidate"
    hr = "hr"
    admin = "admin"


class ApplicationStatus(str, enum.Enum):
    applied = "applied"
    screened = "screened"
    interviewed = "interviewed"
    ranked = "ranked"
    rejected = "rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(SAEnum(UserRole), default=UserRole.candidate, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    resumes: Mapped[list["Resume"]] = relationship("Resume", back_populates="user", cascade="all, delete-orphan")
    interviews: Mapped[list["Interview"]] = relationship("Interview", back_populates="user", cascade="all, delete-orphan")
    rankings: Mapped[list["Ranking"]] = relationship("Ranking", back_populates="user", cascade="all, delete-orphan")
    profile: Mapped["Profile"] = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    settings: Mapped["Settings"] = relationship("Settings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship("Application", back_populates="user", cascade="all, delete-orphan")
    assessments: Mapped[list["Assessment"]] = relationship("Assessment", back_populates="user", cascade="all, delete-orphan")
    mock_interviews: Mapped[list["MockInterview"]] = relationship("MockInterview", back_populates="user", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    required_skills: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    experience_years: Mapped[int] = mapped_column(Integer, default=0)
    weight_resume: Mapped[float] = mapped_column(Float, default=0.30)
    weight_match: Mapped[float] = mapped_column(Float, default=0.30)
    weight_interview: Mapped[float] = mapped_column(Float, default=0.40)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    interviews: Mapped[list["Interview"]] = relationship("Interview", back_populates="job")
    rankings: Mapped[list["Ranking"]] = relationship("Ranking", back_populates="job")
    applications: Mapped[list["Application"]] = relationship("Application", back_populates="job", cascade="all, delete-orphan")


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    parsed_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resume_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    parse_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | done | failed
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="resumes")


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    conversation: Mapped[list] = mapped_column(JSONB, default=list)   # [{role, content, score}]
    interview_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | completed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="interviews")
    job: Mapped["Job"] = relationship("Job", back_populates="interviews")


class Ranking(Base):
    __tablename__ = "rankings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    resume_score: Mapped[float] = mapped_column(Float, default=0.0)
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    interview_score: Mapped[float] = mapped_column(Float, default=0.0)
    final_score: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ApplicationStatus] = mapped_column(SAEnum(ApplicationStatus), default=ApplicationStatus.applied)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="rankings")
    job: Mapped["Job"] = relationship("Job", back_populates="rankings")


class Profile(Base):
    """Extended candidate profile (Candidate Dashboard). 1:1 with User."""
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)        # headline e.g. "Backend Engineer"
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    social_links: Mapped[dict] = mapped_column(JSONB, default=dict)              # {github, linkedin, website}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="profile")


class Settings(Base):
    """Per-user preferences (Candidate Dashboard). 1:1 with User."""
    __tablename__ = "user_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSONB, default=dict)               # {notifications, theme, visibility, ...}
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="settings")


class Application(Base):
    """A candidate's application to a job."""
    __tablename__ = "applications"
    __table_args__ = ()

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False)
    status: Mapped[ApplicationStatus] = mapped_column(SAEnum(ApplicationStatus), default=ApplicationStatus.applied)
    cover_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship("User", back_populates="applications")
    job: Mapped["Job"] = relationship("Job", back_populates="applications")


class Assessment(Base):
    """A skill assessment session and its result."""
    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    skills: Mapped[list] = mapped_column(JSONB, default=list)                    # skills the assessment targets
    questions: Mapped[list] = mapped_column(JSONB, default=list)                 # [{id, prompt, options, answer_index, skill}]
    answers: Mapped[dict] = mapped_column(JSONB, default=dict)                   # {question_id: selected_index}
    score: Mapped[float | None] = mapped_column(Float, nullable=True)           # 0-100
    status: Mapped[str] = mapped_column(String(20), default="in_progress")      # in_progress | completed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="assessments")


class MockInterview(Base):
    """Self-practice interview not tied to a job ranking (Candidate Dashboard)."""
    __tablename__ = "mock_interviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role: Mapped[str | None] = mapped_column(String(160), nullable=True)        # target role for the practice
    skills: Mapped[list] = mapped_column(JSONB, default=list)
    conversation: Mapped[list] = mapped_column(JSONB, default=list)             # [{question, category, answer, answer_score, feedback}]
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")          # active | completed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="mock_interviews")
