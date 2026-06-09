"""GDPR / right-to-erasure: permanently delete a user and all their data.

Removes the account, profile, applications, outreach emails, automation loops &
runs, usage counters, any feedback they submitted (matched by email), and all
files generated/uploaded on their behalf. Shared records (deduplicated `jobs`,
aggregate `api_usage`) are left intact as they contain no personal data.
"""

import logging
import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.database import (
    AutomationLoop,
    AutomationRun,
    Feedback,
    JobApplication,
    OutreachEmail,
    UsageCounter,
    User,
    UserProfile,
)
from app.services import billing

logger = logging.getLogger(__name__)


def _unlink(path: str | None) -> None:
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:  # pragma: no cover - filesystem best-effort
        logger.warning("Could not delete file %s", path)


def _delete_generated_dir(application_id: int) -> None:
    out_dir = Path(settings.generated_dir) / f"app_{application_id}"
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)


def delete_account(db: Session, user: User) -> None:
    """Cancel any subscription and erase every trace of `user`."""
    # 1) Unsubscribe from billing (best-effort; never blocks deletion).
    billing.cancel_subscription(user)

    email = user.email
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()

    if profile:
        applications = (
            db.query(JobApplication)
            .filter(JobApplication.user_profile_id == profile.id)
            .all()
        )
        app_ids = [a.id for a in applications]

        # 2) Remove generated + uploaded files from disk.
        for app in applications:
            _delete_generated_dir(app.id)
            _unlink(app.tailored_cv_path)
            _unlink(app.tailored_cover_letter_path)
        _unlink(profile.cv_path)
        _unlink(profile.baseline_cover_letter_path)

        # 3) Delete dependent rows (children first to satisfy FKs).
        if app_ids:
            db.query(OutreachEmail).filter(
                OutreachEmail.application_id.in_(app_ids)
            ).delete(synchronize_session=False)
        db.query(JobApplication).filter(
            JobApplication.user_profile_id == profile.id
        ).delete(synchronize_session=False)
        db.query(AutomationRun).filter(
            AutomationRun.user_profile_id == profile.id
        ).delete(synchronize_session=False)
        db.query(AutomationLoop).filter(
            AutomationLoop.user_profile_id == profile.id
        ).delete(synchronize_session=False)
        db.query(UsageCounter).filter(
            UsageCounter.user_profile_id == profile.id
        ).delete(synchronize_session=False)

    # 4) Erase any feedback/reviews/contact messages that carry their email.
    if email:
        db.query(Feedback).filter(Feedback.email == email).delete(
            synchronize_session=False
        )

    # 5) Finally the profile and the account itself.
    if profile:
        db.query(UserProfile).filter(UserProfile.id == profile.id).delete(
            synchronize_session=False
        )
    db.query(User).filter(User.id == user.id).delete(synchronize_session=False)
    db.commit()
