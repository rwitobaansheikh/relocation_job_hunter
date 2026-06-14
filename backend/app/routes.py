import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.auth import (
    create_access_token,
    get_current_profile,
    get_current_user,
)
from app.config import settings
from app.database import (
    AutomationLoop,
    AutomationRun,
    Feedback,
    Job,
    JobApplication,
    OutreachEmail,
    User,
    UserProfile,
    UserRole,
    get_db,
)
from app.schemas import (
    AutomationLoopCreate,
    AutomationLoopResponse,
    AutomationLoopUpdate,
    AutomationRunResponse,
    ContactCreate,
    ContactResponse,
    DeleteAccountRequest,
    FollowUpRequest,
    JobApplicationResponse,
    JobImportPreviewResponse,
    JobImportRequest,
    JobSearchRequest,
    LoginRequest,
    ManualJobRequest,
    OutreachEmailResponse,
    RegisterRequest,
    ReviewCreate,
    ReviewPublic,
    RoleSuggestResponse,
    SearchCriteriaSuggestResponse,
    SearchStatsResponse,
    SENIORITY_LEVELS,
    WORK_TYPES,
    SendOutreachRequest,
    SettingsResponse,
    SettingsUpdate,
    TailorDocumentsRequest,
    TailoredDocumentsResponse,
    TokenResponse,
    UserProfileResponse,
    UserProfileUpdate,
    UserResponse,
)
from app.security import encrypt_secret, hash_password, verify_password
from app.services.account import delete_account
from app.services.document_generator import DocumentGenerator
from app.services.cv_link_extractor import build_project_link_map, serialize_project_links
from app.services.document_parser import extract_text_from_file
from app.services.email_finder import EmailFinder
from app.services.email_service import EmailService
from app.services.job_matcher import JobMatcher
from app.services.job_search import JobSearchService, SearchFilters
from app.services.plans import effective_limits
from app.services.role_suggester import suggest_roles
from app.services.search_criteria_suggester import suggest_search_criteria
from app.services.scraper.base import RawJob
from app.services.url_importer import import_job_from_url
from app.services.usage import get_usage, incr_usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])

UPLOAD_DIR = Path(settings.uploads_dir)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _owned_application(
    db: Session, application_id: int, profile: UserProfile, with_job: bool = False
) -> JobApplication:
    """Fetch an application that belongs to the current user, or 404."""
    query = db.query(JobApplication)
    if with_job:
        query = query.options(joinedload(JobApplication.job))
    app = query.filter(JobApplication.id == application_id).first()
    if not app or app.user_profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@auth_router.post("/register", response_model=TokenResponse)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # The very first account becomes an admin so the system is manageable out
    # of the box without needing the env-based bootstrap.
    is_first = db.query(User).count() == 0
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        role=UserRole.ADMIN.value if is_first else UserRole.USER.value,
        is_active=True,
        plan="trial",
        plan_status="trialing",
        trial_end=datetime.utcnow() + timedelta(days=settings.trial_days),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = UserProfile(
        user_id=user.id,
        full_name=data.full_name,
        email=data.email,
        daily_send_cap=settings.default_daily_send_cap,
        per_domain_cap=settings.default_per_domain_cap,
        automation_interval_hours=settings.default_automation_interval_hours,
        max_tailor_per_run=settings.default_max_tailor_per_run,
    )
    db.add(profile)
    db.commit()

    return TokenResponse(access_token=create_access_token(user.id), user=user)


@auth_router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    return TokenResponse(access_token=create_access_token(user.id), user=user)


@auth_router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    return user


@router.delete("/account", status_code=204)
def delete_my_account(
    data: DeleteAccountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """GDPR right-to-erasure: cancel any subscription and permanently delete the
    account and all associated personal data. Irreversible."""
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=403, detail="Password is incorrect")
    delete_account(db, user)
    return None


# --------------------------------------------------------------------------- #
# Feedback / reviews / contact (public, no auth required)
# --------------------------------------------------------------------------- #
@router.get("/reviews", response_model=list[ReviewPublic])
def list_reviews(db: Session = Depends(get_db), limit: int = 20):
    return (
        db.query(Feedback)
        .filter(Feedback.kind == "review", Feedback.approved.is_(True))
        .order_by(Feedback.created_at.desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )


@router.post("/reviews", response_model=ReviewPublic)
def create_review(data: ReviewCreate, db: Session = Depends(get_db)):
    review = Feedback(
        kind="review",
        name=data.name.strip(),
        email=(data.email or ""),
        rating=data.rating,
        message=data.message.strip(),
        approved=True,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@router.post("/contact")
async def submit_contact(data: ContactCreate, db: Session = Depends(get_db)):
    record = Feedback(
        kind="contact",
        name=data.name.strip(),
        email=str(data.email),
        subject=data.subject.strip(),
        message=data.message.strip(),
        approved=True,
    )
    db.add(record)
    db.commit()

    # Best-effort notification to the site owner; never fail the request if the
    # shared mailbox isn't configured (the message is already stored).
    emailed = False
    try:
        subject = f"[Contact] {data.subject.strip() or 'New message'} - {data.name.strip()}"
        body = (
            f"From: {data.name.strip()} <{data.email}>\n"
            f"Subject: {data.subject.strip() or '(none)'}\n\n"
            f"{data.message.strip()}\n"
        )
        await EmailService().send_system_email(settings.contact_email, subject, body)
        emailed = True
    except Exception as exc:  # pragma: no cover - depends on SMTP config
        logger.warning("Contact email could not be delivered: %s", exc)

    return {"ok": True, "emailed": emailed}


# --------------------------------------------------------------------------- #
# Profile (current user)
# --------------------------------------------------------------------------- #
@router.get("/profile", response_model=UserProfileResponse)
def get_profile(profile: UserProfile = Depends(get_current_profile)):
    return profile


@router.patch("/profile", response_model=UserProfileResponse)
def update_profile(
    data: UserProfileUpdate,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/profile/upload-cv", response_model=UserProfileResponse)
async def upload_cv(
    file: UploadFile = File(...),
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    dest = UPLOAD_DIR / f"profile_{profile.id}_cv{Path(file.filename or 'cv.pdf').suffix}"
    async with aiofiles.open(dest, "wb") as f:
        await f.write(await file.read())

    profile.cv_path = str(dest)
    profile.cv_text = extract_text_from_file(str(dest))
    profile.cv_links_json = serialize_project_links(
        build_project_link_map(str(dest), profile.cv_text)
    )
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/profile/upload-cover-letter", response_model=UserProfileResponse)
async def upload_cover_letter(
    file: UploadFile = File(...),
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    dest = UPLOAD_DIR / f"profile_{profile.id}_cover{Path(file.filename or 'cover.pdf').suffix}"
    async with aiofiles.open(dest, "wb") as f:
        await f.write(await file.read())

    profile.baseline_cover_letter_path = str(dest)
    profile.baseline_cover_letter_text = extract_text_from_file(str(dest))
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/profile/suggest-roles", response_model=RoleSuggestResponse)
async def suggest_profile_roles(
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    """Analyze uploaded CV (+ cover letter) and suggest job roles to target."""
    limits = effective_limits(profile.user)
    if get_usage(db, profile.id, "llm") >= limits.llm_per_day:
        raise HTTPException(status_code=429, detail="Daily AI usage limit reached for your plan.")
    incr_usage(db, profile.id, "llm")
    
    roles, message = await suggest_roles(profile)
    return RoleSuggestResponse(roles=roles, message=message)


@router.post("/profile/suggest-search-criteria", response_model=SearchCriteriaSuggestResponse)
async def suggest_profile_search_criteria(
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    """Analyze CV + cover letter and suggest full job-search criteria for high-volume,
    relevant results (roles, locations, seniority, freshness, salary)."""
    limits = effective_limits(profile.user)
    if get_usage(db, profile.id, "llm") >= limits.llm_per_day:
        raise HTTPException(status_code=429, detail="Daily AI usage limit reached for your plan.")
    incr_usage(db, profile.id, "llm")

    criteria, message = await suggest_search_criteria(profile)
    return SearchCriteriaSuggestResponse(message=message, **criteria)


# --------------------------------------------------------------------------- #
# Settings (sending identity + automation)
# --------------------------------------------------------------------------- #
def _settings_response(profile: UserProfile) -> SettingsResponse:
    return SettingsResponse(
        smtp_host=profile.smtp_host or "",
        smtp_port=profile.smtp_port or settings.smtp_port,
        smtp_user=profile.smtp_user or "",
        smtp_from=profile.smtp_from or "",
        smtp_password_set=bool(profile.smtp_password_enc),
        gemini_override_set=bool(profile.gemini_api_key_enc),
        rocketreach_override_set=bool(profile.rocketreach_api_key_enc),
        automation_enabled=bool(profile.automation_enabled),
        automation_interval_hours=profile.automation_interval_hours
        or settings.default_automation_interval_hours,
        daily_send_cap=profile.daily_send_cap
        if profile.daily_send_cap is not None
        else settings.default_daily_send_cap,
        per_domain_cap=profile.per_domain_cap
        if profile.per_domain_cap is not None
        else settings.default_per_domain_cap,
        max_tailor_per_run=profile.max_tailor_per_run
        or settings.default_max_tailor_per_run,
        last_automation_run_at=profile.last_automation_run_at,
    )


@router.get("/settings", response_model=SettingsResponse)
def get_settings(profile: UserProfile = Depends(get_current_profile)):
    return _settings_response(profile)


@router.patch("/settings", response_model=SettingsResponse)
def update_settings(
    data: SettingsUpdate,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    payload = data.model_dump(exclude_unset=True)
    # Secrets: empty string clears, non-empty encrypts, omitted leaves as-is.
    if "smtp_password" in payload:
        profile.smtp_password_enc = encrypt_secret(payload.pop("smtp_password") or "")
    if "gemini_api_key" in payload:
        profile.gemini_api_key_enc = encrypt_secret(payload.pop("gemini_api_key") or "")
    if "rocketreach_api_key" in payload:
        profile.rocketreach_api_key_enc = encrypt_secret(payload.pop("rocketreach_api_key") or "")
    for key, value in payload.items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return _settings_response(profile)


# --------------------------------------------------------------------------- #
# Job search
# --------------------------------------------------------------------------- #
@router.post("/jobs/search")
async def search_jobs(
    request: JobSearchRequest,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    """
    Starts a streaming search that yields jobs as they are found and stored.
    Returns a StreamingResponse with SSE (Server-Sent Events) containing JSON lines.
    """
    service = JobSearchService()
    filters = SearchFilters(
        seniority_levels=[lvl for lvl in request.seniority_levels if lvl in SENIORITY_LEVELS],
        posted_within_hours=request.posted_within_hours,
        min_salary=request.min_salary,
        max_salary=request.max_salary,
        location=request.location,
        roles=[r.strip() for r in request.roles if r and r.strip()],
        work_types=[wt for wt in request.work_types if wt in WORK_TYPES],
    )
    
    # We use an async generator to stream jobs back to the client as they are processed
    async def event_stream():
        try:
            async for event in service.search_jobs_stream(db, profile.id, request.max_jobs, filters):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"Search stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --------------------------------------------------------------------------- #
# Add a job from a link
# --------------------------------------------------------------------------- #
@router.post("/jobs/import", response_model=JobImportPreviewResponse)
async def import_job(
    request: JobImportRequest,
    profile: UserProfile = Depends(get_current_profile),
):
    """Best-effort scrape of a pasted job URL. Returns extracted fields plus a
    `scraped` flag and `missing` list so the UI can ask the user to complete
    anything that couldn't be parsed. Does not persist anything."""
    url = request.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    data = await import_job_from_url(url)
    return JobImportPreviewResponse(**data)


@router.post("/jobs/manual", response_model=JobApplicationResponse)
def add_manual_job(
    request: ManualJobRequest,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    """Create a job + application from user-provided (and/or imported) details."""
    limits = effective_limits(profile.user)
    if get_usage(db, profile.id, "manual") >= limits.manual_per_day:
        raise HTTPException(status_code=429, detail="Daily manual application limit reached for your plan.")
    
    url = request.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url

    matcher = JobMatcher()
    raw = RawJob(
        external_id=f"manual:{url}",
        source="manual",
        title=request.title.strip(),
        company=request.company.strip(),
        url=url,
        description=request.description or "",
        location=request.location or "",
        company_domain=request.company_domain or "",
        posted_at=request.posted_at or datetime.utcnow(),
        tags=[],
    )
    seniority = request.seniority_level or matcher.classify_seniority(raw)
    offers_relocation, relocation_kw = matcher.check_relocation(raw)
    score = matcher.score_relevance(raw, profile)

    existing = db.query(Job).filter(Job.external_id == raw.external_id).first()
    if existing:
        job_record = existing
        job_record.title = raw.title
        job_record.company = raw.company
        job_record.company_domain = raw.company_domain
        job_record.location = raw.location
        job_record.description = raw.description
        job_record.experience_level = seniority
        job_record.seniority_level = seniority
        job_record.offers_relocation = offers_relocation
        job_record.relocation_keywords = relocation_kw
        job_record.salary_min = request.salary_min
        job_record.salary_max = request.salary_max
        job_record.salary_currency = request.salary_currency
        job_record.salary_text = request.salary_text
        job_record.posted_at = raw.posted_at
        job_record.relevance_score = score
    else:
        job_record = Job(
            external_id=raw.external_id,
            source="manual",
            title=raw.title,
            company=raw.company,
            company_domain=raw.company_domain,
            location=raw.location,
            description=raw.description,
            url=url,
            experience_level=seniority,
            seniority_level=seniority,
            offers_relocation=offers_relocation,
            relocation_keywords=relocation_kw,
            salary_min=request.salary_min,
            salary_max=request.salary_max,
            salary_currency=request.salary_currency,
            salary_text=request.salary_text,
            posted_at=raw.posted_at,
            relevance_score=score,
        )
        db.add(job_record)
        db.flush()

    app = (
        db.query(JobApplication)
        .filter(
            JobApplication.user_profile_id == profile.id,
            JobApplication.job_id == job_record.id,
        )
        .first()
    )
    if not app:
        app = JobApplication(
            user_profile_id=profile.id,
            job_id=job_record.id,
            status="discovered",
        )
        db.add(app)
        incr_usage(db, profile.id, "manual")
    db.commit()

    return (
        db.query(JobApplication)
        .options(joinedload(JobApplication.job))
        .filter(JobApplication.id == app.id)
        .first()
    )


# --------------------------------------------------------------------------- #
# Applications (current user)
# --------------------------------------------------------------------------- #
@router.get("/applications", response_model=list[JobApplicationResponse])
def list_applications(
    status: Optional[str] = None,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    query = (
        db.query(JobApplication)
        .options(joinedload(JobApplication.job))
        .filter(JobApplication.user_profile_id == profile.id)
    )
    if status:
        query = query.filter(JobApplication.status == status)
    return query.order_by(JobApplication.created_at.desc()).all()


@router.delete("/applications")
def delete_all_applications(
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    """Remove all job applications (and their outreach emails) for the user."""
    app_ids = [
        a.id
        for a in db.query(JobApplication.id)
        .filter(JobApplication.user_profile_id == profile.id)
        .all()
    ]
    if app_ids:
        db.query(OutreachEmail).filter(
            OutreachEmail.application_id.in_(app_ids)
        ).delete(synchronize_session=False)
        db.query(JobApplication).filter(
            JobApplication.id.in_(app_ids)
        ).delete(synchronize_session=False)
        db.commit()
    return {"deleted": len(app_ids)}


@router.get("/applications/{application_id}", response_model=JobApplicationResponse)
def get_application(
    application_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    return _owned_application(db, application_id, profile, with_job=True)


@router.get("/applications/{application_id}/documents", response_model=TailoredDocumentsResponse)
def get_tailored_documents(
    application_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    """Return metadata and cover letter text for tailored documents."""
    app = _owned_application(db, application_id, profile)
    cv_path = (app.tailored_cv_path or "").strip()
    cl_path = (app.tailored_cover_letter_path or "").strip()

    cover_text = ""
    if app.analysis_json:
        try:
            parsed = json.loads(app.analysis_json)
            cover_text = (parsed.get("cover_letter") or "").strip()
        except Exception:
            pass
    if not cover_text and cl_path and Path(cl_path).exists():
        cover_text = extract_text_from_file(cl_path)

    return TailoredDocumentsResponse(
        has_cv=bool(cv_path and Path(cv_path).exists()),
        has_cover_letter=bool(cl_path and Path(cl_path).exists()),
        cover_letter_text=cover_text,
        cv_filename=Path(cv_path).name if cv_path else "",
        cover_letter_filename=Path(cl_path).name if cl_path else "",
    )


@router.get("/applications/{application_id}/documents/{doc_type}")
def download_tailored_document(
    application_id: int,
    doc_type: str,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    """Download tailored CV or cover letter (authenticated)."""
    app = _owned_application(db, application_id, profile)
    if doc_type == "cv":
        path = (app.tailored_cv_path or "").strip()
        label = "cv"
    elif doc_type in ("cover-letter", "cover_letter"):
        path = (app.tailored_cover_letter_path or "").strip()
        label = "cover-letter"
    else:
        raise HTTPException(status_code=400, detail="Unknown document type")

    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Document not found")

    # Ensure the file lives under our generated/uploads dirs (path traversal guard).
    resolved = Path(path).resolve()
    allowed_roots = [
        Path(settings.generated_dir).resolve(),
        Path(settings.uploads_dir).resolve(),
    ]
    if not any(str(resolved).startswith(str(root)) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Access denied")

    media = "application/pdf" if resolved.suffix.lower() == ".pdf" else "text/plain"
    return FileResponse(
        path=str(resolved),
        media_type=media,
        filename=resolved.name,
        headers={"Content-Disposition": f'inline; filename="{resolved.name}"'},
    )


@router.patch("/applications/{application_id}/status")
def update_application_status(
    application_id: int,
    status: str,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    app = _owned_application(db, application_id, profile)
    app.status = status
    db.commit()
    return {"id": application_id, "status": status}


@router.post("/applications/tailor", response_model=list[JobApplicationResponse])
async def tailor_documents(
    request: TailorDocumentsRequest,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    limits = effective_limits(profile.user)
    
    generator = DocumentGenerator()
    if request.application_ids:
        # Restrict to applications the user actually owns.
        owned = {
            a.id
            for a in db.query(JobApplication.id)
            .filter(
                JobApplication.id.in_(request.application_ids),
                JobApplication.user_profile_id == profile.id,
            )
            .all()
        }
        application_ids = [i for i in request.application_ids if i in owned]
    else:
        apps = (
            db.query(JobApplication)
            .filter(
                JobApplication.user_profile_id == profile.id,
                JobApplication.status == "discovered",
            )
            .limit(20)
            .all()
        )
        application_ids = [a.id for a in apps]

    # Limit by what they have left
    used_tailor = get_usage(db, profile.id, "tailor")
    remaining_tailor = max(0, limits.tailor_per_day - used_tailor)
    
    if len(application_ids) > remaining_tailor:
        application_ids = application_ids[:remaining_tailor]
        
    if not application_ids and request.application_ids:
        raise HTTPException(status_code=429, detail="Daily document tailoring limit reached for your plan.")

    try:
        results = await generator.tailor_batch(db, application_ids)
        for _ in results:
            incr_usage(db, profile.id, "tailor")
        return results
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/applications/{application_id}/tailor", response_model=JobApplicationResponse)
async def tailor_single(
    application_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    limits = effective_limits(profile.user)
    if get_usage(db, profile.id, "tailor") >= limits.tailor_per_day:
        raise HTTPException(status_code=429, detail="Daily document tailoring limit reached for your plan.")

    _owned_application(db, application_id, profile)
    generator = DocumentGenerator()
    try:
        result = await generator.tailor_for_application(db, application_id)
        incr_usage(db, profile.id, "tailor")
        return result
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        # Tailoring failed (e.g. AI rate-limited) - surface as a retryable error.
        raise HTTPException(status_code=503, detail=message)


@router.post("/applications/send-outreach", response_model=list[OutreachEmailResponse])
async def send_outreach(
    request: SendOutreachRequest,
    user: User = Depends(get_current_user),
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    _owned_application(db, request.application_id, profile)

    # A real outreach send (not a preview/test) counts as one manual application
    # against the plan's daily cap.
    is_real_send = not request.dry_run and not request.test_to_self
    if is_real_send:
        limits = effective_limits(user)
        if get_usage(db, profile.id, "manual") >= limits.manual_per_day:
            raise HTTPException(
                status_code=402,
                detail=(
                    f"You've reached your plan's daily limit of {limits.manual_per_day} "
                    "manual applications. Upgrade your plan to apply to more jobs today."
                ),
            )

    service = EmailService()
    try:
        results = await service.send_outreach(
            db, request.application_id, request.dry_run, request.test_to_self
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if is_real_send and any(r.status == "sent" for r in results):
        incr_usage(db, profile.id, "manual", 1)
        db.commit()
    return results


@router.get("/applications/{application_id}/emails", response_model=list[OutreachEmailResponse])
def get_outreach_emails(
    application_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    _owned_application(db, application_id, profile)
    return db.query(OutreachEmail).filter(OutreachEmail.application_id == application_id).all()


@router.get("/applications/{application_id}/contacts", response_model=list[ContactResponse])
async def find_application_contacts(
    application_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    """Look up outreach contacts (emails) for the job's company via Hunter.io."""
    app = _owned_application(db, application_id, profile, with_job=True)
    if not app.job:
        raise HTTPException(status_code=400, detail="Application has no associated job")

    finder = EmailFinder()
    contacts = await finder.find_contacts(
        company=app.job.company,
        domain=app.job.company_domain,
        job_title=app.job.title,
        limit=settings.max_emails_per_company,
    )
    return [
        ContactResponse(name=c.name, email=c.email, title=c.title, confidence=c.confidence)
        for c in contacts
    ]


@router.post("/applications/follow-up")
def schedule_follow_up(
    request: FollowUpRequest,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    app = _owned_application(db, request.application_id, profile)
    now = datetime.utcnow()
    app.last_follow_up_at = now
    app.next_follow_up_at = now + timedelta(days=request.schedule_next_days)
    app.status = "follow_up_sent"
    if request.notes:
        app.notes = (app.notes + "\n" if app.notes else "") + f"[{now.isoformat()}] {request.notes}"
    db.commit()
    return {"id": app.id, "next_follow_up_at": app.next_follow_up_at, "status": app.status}


# --------------------------------------------------------------------------- #
# Automation loops (plan-capped)
# --------------------------------------------------------------------------- #
def _owned_loop(db: Session, loop_id: int, profile: UserProfile) -> AutomationLoop:
    loop = db.query(AutomationLoop).filter(AutomationLoop.id == loop_id).first()
    if not loop or loop.user_profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Automation loop not found")
    return loop


def _active_loop_count(db: Session, profile_id: int) -> int:
    return (
        db.query(AutomationLoop)
        .filter(
            AutomationLoop.user_profile_id == profile_id,
            AutomationLoop.enabled.is_(True),
        )
        .count()
    )


@router.get("/automation/loops", response_model=list[AutomationLoopResponse])
def list_loops(
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    return (
        db.query(AutomationLoop)
        .filter(AutomationLoop.user_profile_id == profile.id)
        .order_by(AutomationLoop.created_at.asc())
        .all()
    )


@router.post("/automation/loops", response_model=AutomationLoopResponse)
def create_loop(
    data: AutomationLoopCreate,
    user: User = Depends(get_current_user),
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    limits = effective_limits(user)
    if not limits.can_automate:
        raise HTTPException(
            status_code=402,
            detail="Your current plan does not include automation. Upgrade to set up automated loops.",
        )
    if data.enabled and _active_loop_count(db, profile.id) >= limits.max_loops:
        raise HTTPException(
            status_code=402,
            detail=(
                f"Your plan allows up to {limits.max_loops} active automation loop(s). "
                "Disable one or upgrade your plan."
            ),
        )
    payload = data.model_dump()
    # Clamp the per-loop daily cap to what the plan allows.
    payload["daily_send_cap"] = min(payload.get("daily_send_cap", 5), limits.auto_per_loop_per_day)
    loop = AutomationLoop(user_profile_id=profile.id, **payload)
    db.add(loop)
    db.commit()
    db.refresh(loop)
    return loop


@router.patch("/automation/loops/{loop_id}", response_model=AutomationLoopResponse)
def update_loop(
    loop_id: int,
    data: AutomationLoopUpdate,
    user: User = Depends(get_current_user),
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    loop = _owned_loop(db, loop_id, profile)
    limits = effective_limits(user)
    payload = data.model_dump(exclude_unset=True)

    # Enabling a loop must respect the plan's active-loop cap.
    if payload.get("enabled") and not loop.enabled:
        if not limits.can_automate:
            raise HTTPException(status_code=402, detail="Your plan does not include automation.")
        if _active_loop_count(db, profile.id) >= limits.max_loops:
            raise HTTPException(
                status_code=402,
                detail=f"Your plan allows up to {limits.max_loops} active automation loop(s).",
            )
    if "daily_send_cap" in payload:
        payload["daily_send_cap"] = min(payload["daily_send_cap"], limits.auto_per_loop_per_day)
    for key, value in payload.items():
        setattr(loop, key, value)
    db.commit()
    db.refresh(loop)
    return loop


@router.delete("/automation/loops/{loop_id}")
def delete_loop(
    loop_id: int,
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    loop = _owned_loop(db, loop_id, profile)
    db.delete(loop)
    db.commit()
    return {"deleted": loop_id}


@router.get("/automation/runs", response_model=list[AutomationRunResponse])
def automation_runs(
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    return (
        db.query(AutomationRun)
        .filter(AutomationRun.user_profile_id == profile.id)
        .order_by(AutomationRun.started_at.desc())
        .limit(10)
        .all()
    )


@router.get("/dashboard/stats")
def dashboard_stats(
    profile: UserProfile = Depends(get_current_profile),
    db: Session = Depends(get_db),
):
    apps = db.query(JobApplication).filter(JobApplication.user_profile_id == profile.id).all()
    return {
        "total": len(apps),
        "discovered": sum(1 for a in apps if a.status == "discovered"),
        "tailored": sum(1 for a in apps if a.status == "tailored"),
        "applied": sum(1 for a in apps if a.status == "applied"),
        "follow_up": sum(1 for a in apps if a.status == "follow_up_sent"),
        "interview": sum(1 for a in apps if a.status == "interview"),
        "rejected": sum(1 for a in apps if a.status == "rejected"),
        "needs_follow_up": sum(
            1 for a in apps if a.next_follow_up_at and a.next_follow_up_at <= datetime.utcnow()
        ),
    }
