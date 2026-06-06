from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


class ApplicationStatus(str, Enum):
    DISCOVERED = "discovered"
    TAILORED = "tailored"
    APPLIED = "applied"
    FOLLOW_UP_SENT = "follow_up_sent"
    REPLIED = "replied"
    REJECTED = "rejected"
    INTERVIEW = "interview"


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=False)
    phone = Column(String(50), default="")
    location = Column(String(200), default="")
    linkedin_url = Column(String(500), default="")
    skills = Column(Text, default="")
    summary = Column(Text, default="")
    cv_path = Column(String(500), default="")
    cv_text = Column(Text, default="")
    baseline_cover_letter_path = Column(String(500), default="")
    baseline_cover_letter_text = Column(Text, default="")
    target_roles = Column(Text, default="")
    target_countries = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    applications = relationship("JobApplication", back_populates="user_profile")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(200), unique=True, index=True)
    source = Column(String(100), nullable=False)
    title = Column(String(300), nullable=False)
    company = Column(String(200), nullable=False)
    company_domain = Column(String(200), default="")
    location = Column(String(300), default="")
    description = Column(Text, default="")
    url = Column(String(1000), nullable=False)
    experience_level = Column(String(50), default="")
    offers_relocation = Column(Boolean, default=False)
    relocation_keywords = Column(Text, default="")
    posted_at = Column(DateTime, nullable=True)
    relevance_score = Column(Float, default=0.0)
    scraped_at = Column(DateTime, default=datetime.utcnow)

    applications = relationship("JobApplication", back_populates="job")


class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(Integer, primary_key=True, index=True)
    user_profile_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    status = Column(String(50), default=ApplicationStatus.DISCOVERED.value)
    tailored_cv_path = Column(String(500), default="")
    tailored_cover_letter_path = Column(String(500), default="")
    notes = Column(Text, default="")
    applied_at = Column(DateTime, nullable=True)
    last_follow_up_at = Column(DateTime, nullable=True)
    next_follow_up_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user_profile = relationship("UserProfile", back_populates="applications")
    job = relationship("Job", back_populates="applications")
    outreach_emails = relationship("OutreachEmail", back_populates="application")


class OutreachEmail(Base):
    __tablename__ = "outreach_emails"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("job_applications.id"), nullable=False)
    recipient_name = Column(String(200), default="")
    recipient_email = Column(String(200), nullable=False)
    recipient_title = Column(String(200), default="")
    subject = Column(String(500), default="")
    body = Column(Text, default="")
    sent_at = Column(DateTime, nullable=True)
    status = Column(String(50), default="pending")
    error_message = Column(Text, default="")

    application = relationship("JobApplication", back_populates="outreach_emails")


engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
