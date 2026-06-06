from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


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
    offers_relocation: bool
    relocation_keywords: str
    posted_at: Optional[datetime]
    relevance_score: float
    scraped_at: datetime

    model_config = {"from_attributes": True}


class JobApplicationResponse(BaseModel):
    id: int
    user_profile_id: int
    job_id: int
    status: str
    tailored_cv_path: str
    tailored_cover_letter_path: str
    notes: str
    applied_at: Optional[datetime]
    last_follow_up_at: Optional[datetime]
    next_follow_up_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    job: Optional[JobResponse] = None

    model_config = {"from_attributes": True}


class OutreachEmailResponse(BaseModel):
    id: int
    application_id: int
    recipient_name: str
    recipient_email: str
    recipient_title: str
    subject: str
    status: str
    sent_at: Optional[datetime]

    model_config = {"from_attributes": True}


class JobSearchRequest(BaseModel):
    user_profile_id: int
    max_jobs: int = Field(default=100, le=100)


class TailorDocumentsRequest(BaseModel):
    application_ids: list[int] = Field(default_factory=list)


class SendOutreachRequest(BaseModel):
    application_id: int
    dry_run: bool = False


class FollowUpRequest(BaseModel):
    application_id: int
    notes: str = ""
    schedule_next_days: int = 7


class SearchStatsResponse(BaseModel):
    jobs_found: int
    jobs_stored: int
    jobs_filtered_relocation: int
    jobs_filtered_experience: int
    jobs_filtered_age: int
