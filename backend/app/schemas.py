from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class DeleteAccountRequest(BaseModel):
    # Password re-confirmation guards against accidental/hijacked deletion.
    # OAuth accounts have no usable password and confirm with "DELETE" instead.
    password: str = ""
    confirm: str = ""  # client sends "DELETE" to acknowledge permanence


class ChangePasswordRequest(BaseModel):
    current_password: str = ""
    new_password: str = Field(min_length=8)


class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    oauth_provider: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class SettingsResponse(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_from: str
    smtp_password_set: bool
    gemini_override_set: bool
    rocketreach_override_set: bool
    automation_enabled: bool
    automation_interval_hours: int
    daily_send_cap: int
    per_domain_cap: int
    max_tailor_per_run: int
    last_automation_run_at: Optional[datetime] = None


class SettingsUpdate(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_password: Optional[str] = None  # plaintext; stored encrypted
    gemini_api_key: Optional[str] = None  # plaintext override; stored encrypted
    rocketreach_api_key: Optional[str] = None  # plaintext override; stored encrypted
    automation_enabled: Optional[bool] = None
    automation_interval_hours: Optional[int] = Field(default=None, ge=1, le=168)
    daily_send_cap: Optional[int] = Field(default=None, ge=0, le=200)
    per_domain_cap: Optional[int] = Field(default=None, ge=1, le=50)
    max_tailor_per_run: Optional[int] = Field(default=None, ge=1, le=50)


class AdminUserResponse(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    created_at: datetime
    profile_name: str = ""
    application_count: int = 0
    emails_sent: int = 0
    automation_enabled: bool = False
    plan: str = ""
    plan_status: str = ""
    trial_end: Optional[datetime] = None
    unlimited_access: bool = False


class AdminUserUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    unlimited_access: Optional[bool] = None


class AdminStatsResponse(BaseModel):
    total_users: int
    active_users: int
    total_applications: int
    emails_sent_today: int
    automation_globally_enabled: bool
    gemini_calls_today: int
    rocketreach_calls_today: int
    automation_users: int


class KillSwitchRequest(BaseModel):
    enabled: bool


# --------------------------------------------------------------------------- #
# Billing
# --------------------------------------------------------------------------- #
class BillingTier(BaseModel):
    id: str
    name: str
    price_usd: int
    price_display: str
    currency: str
    is_estimate: bool
    features: list[str]


class BillingLimits(BaseModel):
    max_loops: int
    auto_per_loop_per_day: int
    manual_per_day: int
    tailor_per_day: int
    llm_per_day: int


class BillingUsage(BaseModel):
    manual_today: int
    loops_active: int
    tailor_today: int
    llm_today: int


class BillingResponse(BaseModel):
    plan: str
    plan_status: str
    trial_end: Optional[datetime] = None
    trial_days_left: int = 0
    trial_days: int = 3
    current_period_end: Optional[datetime] = None
    unlimited_access: bool = False
    is_admin: bool = False
    stripe_configured: bool = False
    has_stripe_subscription: bool = False
    limits: BillingLimits
    usage: BillingUsage
    tiers: list[BillingTier]


class CheckoutRequest(BaseModel):
    tier: str


# --------------------------------------------------------------------------- #
# Feedback / reviews / contact
# --------------------------------------------------------------------------- #
class ReviewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    rating: int = Field(ge=1, le=5)
    message: str = Field(min_length=3, max_length=2000)
    email: Optional[EmailStr] = None


class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    subject: str = Field(default="", max_length=200)
    message: str = Field(min_length=3, max_length=4000)


class ReviewPublic(BaseModel):
    id: int
    name: str
    rating: Optional[int] = None
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackResponse(BaseModel):
    id: int
    kind: str
    name: str
    email: str
    rating: Optional[int] = None
    subject: str
    message: str
    approved: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackUpdate(BaseModel):
    approved: Optional[bool] = None


class CheckoutResponse(BaseModel):
    url: str


# --------------------------------------------------------------------------- #
# Automation loops
# --------------------------------------------------------------------------- #
class AutomationLoopResponse(BaseModel):
    id: int
    name: str
    role: str
    locations: str
    seniority_levels: str
    posted_within_hours: int
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    interval_hours: int
    daily_send_cap: int
    per_domain_cap: int
    max_tailor_per_run: int
    enabled: bool
    last_run_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AutomationLoopCreate(BaseModel):
    name: str = ""
    role: str = Field(default="", max_length=200)
    locations: str = ""
    seniority_levels: str = ""
    posted_within_hours: int = Field(default=24, ge=1, le=2160)
    min_salary: Optional[int] = Field(default=None, ge=0)
    max_salary: Optional[int] = Field(default=None, ge=0)
    interval_hours: int = Field(default=24, ge=1, le=168)
    daily_send_cap: int = Field(default=5, ge=0, le=500)
    per_domain_cap: int = Field(default=2, ge=1, le=50)
    max_tailor_per_run: int = Field(default=5, ge=1, le=50)
    enabled: bool = True


class AutomationLoopUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = Field(default=None, max_length=200)
    locations: Optional[str] = None
    seniority_levels: Optional[str] = None
    posted_within_hours: Optional[int] = Field(default=None, ge=1, le=2160)
    min_salary: Optional[int] = Field(default=None, ge=0)
    max_salary: Optional[int] = Field(default=None, ge=0)
    interval_hours: Optional[int] = Field(default=None, ge=1, le=168)
    daily_send_cap: Optional[int] = Field(default=None, ge=0, le=500)
    per_domain_cap: Optional[int] = Field(default=None, ge=1, le=50)
    max_tailor_per_run: Optional[int] = Field(default=None, ge=1, le=50)
    enabled: Optional[bool] = None


class AutomationRunResponse(BaseModel):
    id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    jobs_found: int
    jobs_tailored: int
    emails_sent: int
    detail: str = ""

    model_config = {"from_attributes": True}


class UserProfileCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    skills: str = ""
    summary: str = ""
    target_roles: str = ""
    target_countries: str = ""


class RoleSuggestResponse(BaseModel):
    roles: list[str]
    message: str = ""


class SearchCriteriaSuggestResponse(BaseModel):
    roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    seniority_levels: list[str] = Field(default_factory=list)
    posted_within_hours: int = 168
    min_salary: Optional[int] = None
    max_salary: Optional[int] = None
    summary: str = ""
    message: str = ""


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    skills: Optional[str] = None
    summary: Optional[str] = None
    target_roles: Optional[str] = None
    target_countries: Optional[str] = None


class UserProfileResponse(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str
    location: str
    linkedin_url: str
    skills: str
    summary: str
    cv_path: str
    baseline_cover_letter_path: str
    target_roles: str
    target_countries: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobResponse(BaseModel):
    id: int
    external_id: str
    source: str
    title: str
    company: str
    company_domain: str
    location: str
    description: str
    url: str
    experience_level: str
    seniority_level: str = ""
    offers_relocation: bool
    relocation_keywords: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = ""
    salary_text: str = ""
    posted_at: Optional[datetime]
    relevance_score: float
    scraped_at: datetime

    model_config = {"from_attributes": True}


class TailoredDocumentsResponse(BaseModel):
    has_cv: bool = False
    has_cover_letter: bool = False
    cover_letter_text: str = ""
    cv_preview: Optional[dict] = None
    cv_filename: str = ""
    cover_letter_filename: str = ""


class CoverLetterUpdateRequest(BaseModel):
    text: str = Field(min_length=10, max_length=8000)


class JobApplicationResponse(BaseModel):
    id: int
    user_profile_id: int
    job_id: int
    status: str
    tailored_cv_path: str
    tailored_cover_letter_path: str
    ai_match_score: int = 0
    analysis_json: str = ""
    notes: str
    applied_at: Optional[datetime]
    last_follow_up_at: Optional[datetime]
    next_follow_up_at: Optional[datetime]
    automation_batch_date: str = ""
    created_at: datetime
    updated_at: datetime
    job: Optional[JobResponse] = None

    model_config = {"from_attributes": True}


class JobImportRequest(BaseModel):
    url: str = Field(min_length=4)


class JobImportPreviewResponse(BaseModel):
    url: str
    title: str = ""
    company: str = ""
    company_domain: str = ""
    location: str = ""
    description: str = ""
    posted_at: Optional[datetime] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = ""
    salary_text: str = ""
    scraped: bool = False
    missing: list[str] = Field(default_factory=list)
    message: str = ""


class ManualJobRequest(BaseModel):
    url: str = Field(min_length=4)
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    location: str = ""
    description: str = ""
    company_domain: str = ""
    posted_at: Optional[datetime] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = ""
    salary_text: str = ""
    seniority_level: str = ""


class ContactResponse(BaseModel):
    name: str
    email: str
    title: str
    confidence: int = 0
    pattern: str = ""
    verification_status: str = ""
    catch_all: bool = False


class ContactsLookupResponse(BaseModel):
    contacts: list[ContactResponse]
    resolved_domain: str = ""
    company: str = ""
    domain_was_job_board: bool = False
    message: str = ""
    sources_used: list[str] = Field(default_factory=list)


class RecruitingEmailFindRequest(BaseModel):
    """Find HR/recruiting emails. Provide at least one of company, website, or job_url."""
    company: str = ""
    website: str = ""
    job_url: str = ""


class UpdateCompanyDomainRequest(BaseModel):
    company_domain: str = Field(min_length=3, max_length=253)


class OutreachEmailResponse(BaseModel):
    id: int
    application_id: int
    recipient_name: str
    recipient_email: str
    recipient_title: str
    subject: str
    body: str
    status: str
    error_message: str
    sent_at: Optional[datetime]

    model_config = {"from_attributes": True}


SENIORITY_LEVELS = ("intern", "entry", "mid", "senior", "executive")
WORK_TYPES = ("remote", "hybrid", "onsite")


class JobSearchRequest(BaseModel):
    max_jobs: int = Field(default=100)
    seniority_levels: list[str] = Field(default_factory=list)
    posted_within_hours: int = Field(default=24, ge=1, le=2160)
    min_salary: Optional[int] = Field(default=None, ge=0)
    max_salary: Optional[int] = Field(default=None, ge=0)
    # The UI now sends one location at a time to strictly enforce location scoping.
    location: str = ""
    roles: list[str] = Field(default_factory=list)
    work_types: list[str] = Field(default_factory=list)


class TailorDocumentsRequest(BaseModel):
    application_ids: list[int] = Field(default_factory=list)


class SendOutreachRequest(BaseModel):
    application_id: int
    dry_run: bool = False
    test_to_self: bool = False


class SendOutreachBatchRequest(BaseModel):
    application_ids: list[int] = Field(min_length=1, max_length=50)
    dry_run: bool = False


class OutreachDraftResponse(BaseModel):
    subject: str
    body: str


class FollowUpRequest(BaseModel):
    application_id: int
    notes: str = ""
    schedule_next_days: int = 7


class SearchStatsResponse(BaseModel):
    jobs_found: int
    jobs_stored: int
