"""Admin console API: user management, system stats, automation kill-switch."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.config import settings
from app.database import (
    ApiUsage,
    AutomationRun,  # noqa: F401  (ensures table is registered)
    Feedback,
    JobApplication,
    OutreachEmail,
    User,
    UserProfile,
    UserRole,
    get_db,
)
from app.schemas import (
    AdminStatsResponse,
    AdminUserResponse,
    AdminUserUpdate,
    FeedbackResponse,
    FeedbackUpdate,
    KillSwitchRequest,
)
from app.services.plans import current_plan

admin_router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])

_SENT_STATUSES = ("sent", "test_sent")


def _today() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


@admin_router.get("/users", response_model=list[AdminUserResponse])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    out: list[AdminUserResponse] = []
    for user in users:
        profile = user.profile
        app_count = 0
        emails_sent = 0
        if profile:
            app_ids = [
                a.id
                for a in db.query(JobApplication.id)
                .filter(JobApplication.user_profile_id == profile.id)
                .all()
            ]
            app_count = len(app_ids)
            if app_ids:
                emails_sent = (
                    db.query(OutreachEmail)
                    .filter(
                        OutreachEmail.application_id.in_(app_ids),
                        OutreachEmail.status.in_(_SENT_STATUSES),
                    )
                    .count()
                )
        out.append(
            AdminUserResponse(
                id=user.id,
                email=user.email,
                role=user.role,
                is_active=user.is_active,
                created_at=user.created_at,
                profile_name=profile.full_name if profile else "",
                application_count=app_count,
                emails_sent=emails_sent,
                automation_enabled=bool(profile.automation_enabled) if profile else False,
                plan=current_plan(user),
                plan_status=user.plan_status or "",
                trial_end=user.trial_end,
                unlimited_access=bool(user.unlimited_access),
            )
        )
    return out


@admin_router.patch("/users/{user_id}", response_model=AdminUserResponse)
def update_user(
    user_id: int,
    data: AdminUserUpdate,
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if data.role is not None:
        if data.role not in {r.value for r in UserRole}:
            raise HTTPException(status_code=400, detail="Invalid role")
        user.role = data.role
    if data.is_active is not None:
        if user.id == admin.id and not data.is_active:
            raise HTTPException(status_code=400, detail="You cannot disable your own account")
        user.is_active = data.is_active
    if data.unlimited_access is not None:
        user.unlimited_access = data.unlimited_access
    db.commit()
    db.refresh(user)

    profile = user.profile
    return AdminUserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        profile_name=profile.full_name if profile else "",
        automation_enabled=bool(profile.automation_enabled) if profile else False,
        plan=current_plan(user),
        plan_status=user.plan_status or "",
        trial_end=user.trial_end,
        unlimited_access=bool(user.unlimited_access),
    )


@admin_router.get("/stats", response_model=AdminStatsResponse)
def stats(db: Session = Depends(get_db)):
    today = _today()
    today_start = datetime.strptime(today, "%Y-%m-%d")

    llm_usage = (
        db.query(ApiUsage)
        .filter(ApiUsage.api.in_(("llm", "gemini")), ApiUsage.day == today)
        .all()
    )
    llm_calls = sum(row.count or 0 for row in llm_usage)
    rocketreach = (
        db.query(ApiUsage).filter(ApiUsage.api == "rocketreach", ApiUsage.day == today).first()
    )

    return AdminStatsResponse(
        total_users=db.query(User).count(),
        active_users=db.query(User).filter(User.is_active.is_(True)).count(),
        total_applications=db.query(JobApplication).count(),
        emails_sent_today=db.query(OutreachEmail)
        .filter(
            OutreachEmail.status.in_(_SENT_STATUSES),
            OutreachEmail.sent_at >= today_start,
        )
        .count(),
        automation_globally_enabled=settings.automation_globally_enabled,
        gemini_calls_today=llm_calls,
        rocketreach_calls_today=rocketreach.count if rocketreach else 0,
        automation_users=db.query(UserProfile)
        .filter(UserProfile.automation_enabled.is_(True))
        .count(),
    )


@admin_router.post("/automation/kill-switch", response_model=AdminStatsResponse)
def set_kill_switch(
    data: KillSwitchRequest,
    db: Session = Depends(get_db),
):
    # Runtime toggle of the global automation switch (in-memory singleton).
    settings.automation_globally_enabled = data.enabled
    return stats(db)


# --------------------------------------------------------------------------- #
# Feedback moderation (reviews + contact messages)
# --------------------------------------------------------------------------- #
@admin_router.get("/feedback", response_model=list[FeedbackResponse])
def list_feedback(db: Session = Depends(get_db), kind: str | None = None):
    query = db.query(Feedback)
    if kind in ("review", "contact"):
        query = query.filter(Feedback.kind == kind)
    return query.order_by(Feedback.created_at.desc()).all()


@admin_router.patch("/feedback/{feedback_id}", response_model=FeedbackResponse)
def update_feedback(
    feedback_id: int,
    data: FeedbackUpdate,
    db: Session = Depends(get_db),
):
    item = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Feedback not found")
    if data.approved is not None:
        item.approved = data.approved
    db.commit()
    db.refresh(item)
    return item


@admin_router.delete("/feedback/{feedback_id}")
def delete_feedback(feedback_id: int, db: Session = Depends(get_db)):
    item = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Feedback not found")
    db.delete(item)
    db.commit()
    return {"deleted": feedback_id}
