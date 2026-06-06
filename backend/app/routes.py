from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import JobApplication, OutreachEmail, UserProfile, get_db
from app.schemas import (
    ContactResponse,
    FollowUpRequest,
    JobApplicationResponse,
    JobSearchRequest,
    OutreachEmailResponse,
    SearchStatsResponse,
    SendOutreachRequest,
    TailorDocumentsRequest,
    UserProfileCreate,
    UserProfileResponse,
    UserProfileUpdate,
)
from app.services.document_generator import DocumentGenerator
from app.services.document_parser import extract_text_from_file
from app.services.email_finder import EmailFinder
from app.services.email_service import EmailService
from app.services.job_search import JobSearchService

router = APIRouter(prefix="/api", tags=["api"])

UPLOAD_DIR = Path(settings.uploads_dir)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/profiles", response_model=UserProfileResponse)
def create_profile(data: UserProfileCreate, db: Session = Depends(get_db)):
    profile = UserProfile(**data.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/profiles", response_model=list[UserProfileResponse])
def list_profiles(db: Session = Depends(get_db)):
    return db.query(UserProfile).order_by(UserProfile.created_at.desc()).all()


@router.get("/profiles/{profile_id}", response_model=UserProfileResponse)
def get_profile(profile_id: int, db: Session = Depends(get_db)):
    profile = db.query(UserProfile).filter(UserProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.patch("/profiles/{profile_id}", response_model=UserProfileResponse)
def update_profile(profile_id: int, data: UserProfileUpdate, db: Session = Depends(get_db)):
    profile = db.query(UserProfile).filter(UserProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/profiles/{profile_id}/upload-cv", response_model=UserProfileResponse)
async def upload_cv(profile_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    profile = db.query(UserProfile).filter(UserProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    dest = UPLOAD_DIR / f"profile_{profile_id}_cv{Path(file.filename or 'cv.pdf').suffix}"
    async with aiofiles.open(dest, "wb") as f:
        content = await file.read()
        await f.write(content)

    profile.cv_path = str(dest)
    profile.cv_text = extract_text_from_file(str(dest))
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/profiles/{profile_id}/upload-cover-letter", response_model=UserProfileResponse)
async def upload_cover_letter(
    profile_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)
):
    profile = db.query(UserProfile).filter(UserProfile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    dest = UPLOAD_DIR / f"profile_{profile_id}_cover{Path(file.filename or 'cover.pdf').suffix}"
    async with aiofiles.open(dest, "wb") as f:
        content = await file.read()
        await f.write(content)

    profile.baseline_cover_letter_path = str(dest)
    profile.baseline_cover_letter_text = extract_text_from_file(str(dest))
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/jobs/search", response_model=SearchStatsResponse)
async def search_jobs(request: JobSearchRequest, db: Session = Depends(get_db)):
    service = JobSearchService()
    try:
        stats = await service.search_jobs(db, request.user_profile_id, request.max_jobs)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return SearchStatsResponse(**stats)


@router.get("/applications", response_model=list[JobApplicationResponse])
def list_applications(
    profile_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(JobApplication).options(joinedload(JobApplication.job))
    if profile_id:
        query = query.filter(JobApplication.user_profile_id == profile_id)
    if status:
        query = query.filter(JobApplication.status == status)
    return query.order_by(JobApplication.created_at.desc()).all()


@router.delete("/applications")
def delete_all_applications(profile_id: int, db: Session = Depends(get_db)):
    """Remove all job applications (and their outreach emails) for a profile."""
    app_ids = [
        a.id
        for a in db.query(JobApplication.id)
        .filter(JobApplication.user_profile_id == profile_id)
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
def get_application(application_id: int, db: Session = Depends(get_db)):
    app = (
        db.query(JobApplication)
        .options(joinedload(JobApplication.job))
        .filter(JobApplication.id == application_id)
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.patch("/applications/{application_id}/status")
def update_application_status(application_id: int, status: str, db: Session = Depends(get_db)):
    app = db.query(JobApplication).filter(JobApplication.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    app.status = status
    db.commit()
    return {"id": application_id, "status": status}


@router.post("/applications/tailor", response_model=list[JobApplicationResponse])
async def tailor_documents(request: TailorDocumentsRequest, db: Session = Depends(get_db)):
    generator = DocumentGenerator()
    if not request.application_ids:
        apps = (
            db.query(JobApplication)
            .filter(JobApplication.status == "discovered")
            .limit(20)
            .all()
        )
        request.application_ids = [a.id for a in apps]

    results = await generator.tailor_batch(db, request.application_ids)
    return results


@router.post("/applications/{application_id}/tailor", response_model=JobApplicationResponse)
async def tailor_single(application_id: int, db: Session = Depends(get_db)):
    generator = DocumentGenerator()
    try:
        return await generator.tailor_for_application(db, application_id)
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message)
        # Tailoring failed (e.g. AI rate-limited) - surface as a retryable error.
        raise HTTPException(status_code=503, detail=message)


@router.post("/applications/send-outreach", response_model=list[OutreachEmailResponse])
async def send_outreach(request: SendOutreachRequest, db: Session = Depends(get_db)):
    service = EmailService()
    try:
        return await service.send_outreach(
            db, request.application_id, request.dry_run, request.test_to_self
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/applications/{application_id}/emails", response_model=list[OutreachEmailResponse])
def get_outreach_emails(application_id: int, db: Session = Depends(get_db)):
    return db.query(OutreachEmail).filter(OutreachEmail.application_id == application_id).all()


@router.get("/applications/{application_id}/contacts", response_model=list[ContactResponse])
async def find_application_contacts(application_id: int, db: Session = Depends(get_db)):
    """Look up outreach contacts (emails) for the job's company via Hunter.io."""
    app = (
        db.query(JobApplication)
        .options(joinedload(JobApplication.job))
        .filter(JobApplication.id == application_id)
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
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
def schedule_follow_up(request: FollowUpRequest, db: Session = Depends(get_db)):
    app = db.query(JobApplication).filter(JobApplication.id == request.application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    now = datetime.utcnow()
    app.last_follow_up_at = now
    app.next_follow_up_at = now + timedelta(days=request.schedule_next_days)
    app.status = "follow_up_sent"
    if request.notes:
        app.notes = (app.notes + "\n" if app.notes else "") + f"[{now.isoformat()}] {request.notes}"
    db.commit()
    return {"id": app.id, "next_follow_up_at": app.next_follow_up_at, "status": app.status}


@router.get("/dashboard/stats")
def dashboard_stats(profile_id: int, db: Session = Depends(get_db)):
    apps = db.query(JobApplication).filter(JobApplication.user_profile_id == profile_id).all()
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
