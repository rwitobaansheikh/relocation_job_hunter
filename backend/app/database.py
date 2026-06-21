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
    UniqueConstraint,
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


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(200), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default=UserRole.USER.value)
    is_active = Column(Boolean, default=True)

    # --- Billing / subscription ---
    plan = Column(String(20), default="trial")  # trial|basic|standard|pro
    plan_status = Column(String(20), default="trialing")  # Stripe subscription status
    trial_end = Column(DateTime, nullable=True)
    stripe_customer_id = Column(String(100), default="")
    stripe_subscription_id = Column(String(100), default="")
    current_period_end = Column(DateTime, nullable=True)
    # Admin-granted unrestricted access (dev/QA superusers).
    unlimited_access = Column(Boolean, default=False)
    # OAuth sign-in provider (google|linkedin); empty for email/password accounts.
    oauth_provider = Column(String(20), default="")
    # Trial lifecycle emails (avoid duplicate sends).
    trial_reminder_sent = Column(Boolean, default=False)
    trial_expired_email_sent = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("UserProfile", back_populates="user", uselist=False)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    full_name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=False)
    phone = Column(String(50), default="")
    location = Column(String(200), default="")
    linkedin_url = Column(String(500), default="")
    skills = Column(Text, default="")
    summary = Column(Text, default="")
    cv_path = Column(String(500), default="")
    cv_text = Column(Text, default="")
    # Hyperlinks extracted from the uploaded CV (PDF annotations + text URLs).
    cv_links_json = Column(Text, default="")
    baseline_cover_letter_path = Column(String(500), default="")
    baseline_cover_letter_text = Column(Text, default="")
    target_roles = Column(Text, default="")
    target_countries = Column(Text, default="")

    # --- Per-user sending identity (hybrid model: own email, shared AI keys) ---
    smtp_host = Column(String(200), default="")
    smtp_port = Column(Integer, default=587)
    smtp_user = Column(String(200), default="")
    smtp_password_enc = Column(Text, default="")
    smtp_from = Column(String(200), default="")
    # Optional encrypted overrides for the otherwise-shared API keys.
    gemini_api_key_enc = Column(Text, default="")
    rocketreach_api_key_enc = Column(Text, default="")

    # --- Automation preferences ---
    automation_enabled = Column(Boolean, default=False)
    automation_interval_hours = Column(Integer, default=12)
    daily_send_cap = Column(Integer, default=20)
    per_domain_cap = Column(Integer, default=2)
    max_tailor_per_run = Column(Integer, default=5)
    last_automation_run_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="profile")
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
    seniority_level = Column(String(20), default="")  # intern|entry|mid|senior|executive
    offers_relocation = Column(Boolean, default=False)
    relocation_keywords = Column(Text, default="")
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    salary_currency = Column(String(8), default="")
    salary_text = Column(String(200), default="")
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
    ai_match_score = Column(Integer, default=0)
    analysis_json = Column(Text, default="")
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


class ApiUsage(Base):
    """Per-day call counter for the shared external APIs (global rate budget)."""

    __tablename__ = "api_usage"
    __table_args__ = (UniqueConstraint("api", "day", name="uq_api_usage_api_day"),)

    id = Column(Integer, primary_key=True, index=True)
    api = Column(String(50), nullable=False)  # "gemini" | "hunter" | "smtp"
    day = Column(String(10), nullable=False)  # "YYYY-MM-DD" (UTC)
    count = Column(Integer, default=0)


class AutomationLoop(Base):
    """A single automated search->tailor->send pipeline for one job role. Plans
    cap how many loops a user may run concurrently."""

    __tablename__ = "automation_loops"

    id = Column(Integer, primary_key=True, index=True)
    user_profile_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=False, index=True)
    name = Column(String(120), default="")
    role = Column(String(200), default="")  # the single target role keyword
    locations = Column(Text, default="")  # csv; falls back to profile countries
    seniority_levels = Column(Text, default="")  # csv of intern|entry|mid|senior|executive
    posted_within_hours = Column(Integer, default=48)
    min_salary = Column(Integer, nullable=True)
    max_salary = Column(Integer, nullable=True)
    interval_hours = Column(Integer, default=12)
    daily_send_cap = Column(Integer, default=5)  # clamped to the plan's auto cap
    per_domain_cap = Column(Integer, default=2)
    max_tailor_per_run = Column(Integer, default=5)
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UsageCounter(Base):
    """Per-user, per-day counter used to enforce manual and per-loop send caps.
    scope is "manual" or "loop:{loop_id}"."""

    __tablename__ = "usage_counters"
    __table_args__ = (
        UniqueConstraint("user_profile_id", "day", "scope", name="uq_usage_user_day_scope"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_profile_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=False, index=True)
    day = Column(String(10), nullable=False)  # YYYY-MM-DD (UTC)
    scope = Column(String(40), nullable=False)
    count = Column(Integer, default=0)


class Feedback(Base):
    """User-submitted reviews and contact-us messages (public, unauthenticated).

    kind = "review" (with a 1-5 rating, shown on the landing page once approved)
    or "contact" (a message routed to the site owner's inbox)."""

    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(20), default="review")  # review | contact
    name = Column(String(120), default="")
    email = Column(String(200), default="")
    rating = Column(Integer, nullable=True)  # 1-5 for reviews
    subject = Column(String(200), default="")
    message = Column(Text, default="")
    approved = Column(Boolean, default=True)  # reviews shown publicly when True
    created_at = Column(DateTime, default=datetime.utcnow)


class AutomationRun(Base):
    """Audit record for one automation pass over a single user's pipeline."""

    __tablename__ = "automation_runs"

    id = Column(Integer, primary_key=True, index=True)
    user_profile_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=False, index=True)
    automation_loop_id = Column(Integer, ForeignKey("automation_loops.id"), nullable=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="running")  # running | success | error
    jobs_found = Column(Integer, default=0)
    jobs_tailored = Column(Integer, default=0)
    emails_sent = Column(Integer, default=0)
    detail = Column(Text, default="")


engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Columns added after the original schema shipped. create_all() will not ALTER
# existing tables, so we add any missing ones by hand for SQLite databases.
_MIGRATIONS: dict[str, dict[str, str]] = {
    "users": {
        "plan": "VARCHAR(20) DEFAULT 'trial'",
        "plan_status": "VARCHAR(20) DEFAULT 'trialing'",
        "trial_end": "DATETIME",
        "stripe_customer_id": "VARCHAR(100) DEFAULT ''",
        "stripe_subscription_id": "VARCHAR(100) DEFAULT ''",
        "current_period_end": "DATETIME",
        "unlimited_access": "BOOLEAN DEFAULT 0",
        "oauth_provider": "VARCHAR(20) DEFAULT ''",
        "trial_reminder_sent": "BOOLEAN DEFAULT 0",
        "trial_expired_email_sent": "BOOLEAN DEFAULT 0",
    },
    "automation_runs": {
        "automation_loop_id": "INTEGER",
    },
    "job_applications": {
        "ai_match_score": "INTEGER DEFAULT 0",
        "analysis_json": "TEXT DEFAULT ''",
    },
    "jobs": {
        "seniority_level": "VARCHAR(20) DEFAULT ''",
        "salary_min": "INTEGER",
        "salary_max": "INTEGER",
        "salary_currency": "VARCHAR(8) DEFAULT ''",
        "salary_text": "VARCHAR(200) DEFAULT ''",
    },
    "user_profiles": {
        "user_id": "INTEGER",
        "smtp_host": "VARCHAR(200) DEFAULT ''",
        "smtp_port": "INTEGER DEFAULT 587",
        "smtp_user": "VARCHAR(200) DEFAULT ''",
        "smtp_password_enc": "TEXT DEFAULT ''",
        "smtp_from": "VARCHAR(200) DEFAULT ''",
        "gemini_api_key_enc": "TEXT DEFAULT ''",
        "rocketreach_api_key_enc": "TEXT DEFAULT ''",
        "automation_enabled": "BOOLEAN DEFAULT 0",
        "automation_interval_hours": "INTEGER DEFAULT 12",
        "daily_send_cap": "INTEGER DEFAULT 20",
        "per_domain_cap": "INTEGER DEFAULT 2",
        "max_tailor_per_run": "INTEGER DEFAULT 5",
        "last_automation_run_at": "DATETIME",
        "cv_links_json": "TEXT DEFAULT ''",
    },
}


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    _bootstrap_admin()
    _migrate_legacy_automation()


def _migrate_legacy_automation() -> None:
    """One-time: turn any pre-existing single-loop automation (fields on
    UserProfile) into an AutomationLoop row so nothing silently stops running."""
    db = SessionLocal()
    try:
        legacy = (
            db.query(UserProfile)
            .filter(UserProfile.automation_enabled.is_(True))
            .all()
        )
        for profile in legacy:
            has_loop = (
                db.query(AutomationLoop)
                .filter(AutomationLoop.user_profile_id == profile.id)
                .first()
            )
            if has_loop:
                continue
            first_role = next(
                (r.strip() for r in (profile.target_roles or "").split(",") if r.strip()),
                "",
            )
            db.add(
                AutomationLoop(
                    user_profile_id=profile.id,
                    name=first_role or "My automation",
                    role=first_role,
                    locations=profile.target_countries or "",
                    interval_hours=profile.automation_interval_hours or 12,
                    daily_send_cap=profile.daily_send_cap or 5,
                    per_domain_cap=profile.per_domain_cap or 2,
                    max_tailor_per_run=profile.max_tailor_per_run or 5,
                    enabled=True,
                    last_run_at=profile.last_automation_run_at,
                )
            )
            # Disable the legacy flag so we don't double-run.
            profile.automation_enabled = False
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _ensure_columns() -> None:
    """Lightweight migration: add new columns to pre-existing SQLite tables."""
    try:
        with engine.connect() as conn:
            for table, columns in _MIGRATIONS.items():
                try:
                    existing = {
                        row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
                    }
                except Exception:
                    continue
                if not existing:
                    continue  # table doesn't exist yet; create_all handled it
                for column, ddl in columns.items():
                    if column not in existing:
                        conn.exec_driver_sql(
                            f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"
                        )
            conn.commit()
    except Exception:
        # Non-SQLite backends or race conditions: create_all already handles the
        # fresh-DB case, so failing here is non-fatal.
        pass


def _bootstrap_admin() -> None:
    """Create the configured admin user (if any) and attach any pre-existing
    orphan profile (from the single-user prototype) to it."""
    from app.security import hash_password  # local import to avoid cycle

    if not settings.admin_email or not settings.admin_password:
        return
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == settings.admin_email).first()
        if not admin:
            admin = User(
                email=settings.admin_email,
                password_hash=hash_password(settings.admin_password),
                role=UserRole.ADMIN.value,
                is_active=True,
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
        # Adopt orphan profiles (the prototype's single profile) under the admin.
        if not admin.profile:
            orphan = db.query(UserProfile).filter(UserProfile.user_id.is_(None)).first()
            if orphan:
                orphan.user_id = admin.id
            else:
                # No profile to adopt: give the admin an empty one so profile
                # routes work out of the box.
                db.add(
                    UserProfile(
                        user_id=admin.id,
                        full_name=settings.admin_email.split("@")[0] or "Admin",
                        email=settings.admin_email,
                    )
                )
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
