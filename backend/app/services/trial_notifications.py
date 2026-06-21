"""Trial expiry reminders and post-expiry upgrade prompts via email."""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.database import User
from app.services.plans import current_plan
from app.services.system_email import send_system_email

logger = logging.getLogger(__name__)


def _billing_url() -> str:
    return f"{settings.app_base_url.rstrip('/')}/app/billing"


def send_trial_ending_email(user: User) -> tuple[str, str, str, str | None]:
    """Return (to, subject, text, html) for trial ending notice."""
    days = settings.trial_days
    subject = f"Your {days}-day free trial ends soon — Job Application Flow"
    text = (
        f"Hi,\n\n"
        f"Your free trial on Job Application Flow ends in about 24 hours. "
        f"Your saved payment method will be charged for the Basic plan when the trial ends "
        f"unless you cancel from the billing portal.\n\n"
        f"Manage your subscription: {_billing_url()}\n\n"
        f"— Job Application Flow"
    )
    html = (
        f"<p>Hi,</p>"
        f"<p>Your <strong>{days}-day free trial</strong> on Job Application Flow ends in about "
        f"<strong>24 hours</strong>. Your saved payment method will be charged for the "
        f"<strong>Basic plan</strong> when the trial ends unless you cancel from the billing portal.</p>"
        f'<p><a href="{_billing_url()}">Manage subscription →</a></p>'
        f"<p>— Job Application Flow</p>"
    )
    return user.email, subject, text, html


def send_trial_expired_email(user: User) -> tuple[str, str, str, str | None]:
    """Return (to, subject, text, html) for trial expired notice."""
    subject = "Your Job Application Flow trial has ended — subscribe to continue"
    text = (
        f"Hi,\n\n"
        f"Your free trial has ended and your account is now locked. "
        f"Subscribe to keep tailoring CVs, sending outreach, and running automation.\n\n"
        f"Choose a plan: {_billing_url()}\n\n"
        f"— Job Application Flow"
    )
    html = (
        f"<p>Hi,</p>"
        f"<p>Your <strong>free trial has ended</strong>. Tailoring, outreach, and automation are "
        f"paused until you subscribe.</p>"
        f'<p><a href="{_billing_url()}">Choose a plan →</a></p>'
        f"<p>— Job Application Flow</p>"
    )
    return user.email, subject, text, html


async def process_trial_notifications(db: Session) -> int:
    """Scan users and send reminder/expired emails. Returns count processed."""
    now = datetime.utcnow()
    processed = 0
    users = (
        db.query(User)
        .filter(User.is_active.is_(True), User.unlimited_access.is_(False))
        .all()
    )
    for user in users:
        if user.role == "admin":
            continue
        plan = current_plan(user)

        # Internal trial: warn 1 day before expiry.
        if (
            plan == "trial"
            and user.trial_end
            and not user.trial_reminder_sent
            and user.trial_end - now <= timedelta(days=1)
            and user.trial_end > now
        ):
            to, subject, text, html = send_trial_ending_email(user)
            ok, err = await send_system_email(to, subject, text, html)
            if not ok:
                logger.warning("Trial ending email failed for %s: %s", to, err)
            else:
                user.trial_reminder_sent = True
                processed += 1
            continue

        # Internal trial or lapsed subscription: expired email once.
        if plan == "expired" and not user.trial_expired_email_sent:
            to, subject, text, html = send_trial_expired_email(user)
            ok, err = await send_system_email(to, subject, text, html)
            if not ok:
                logger.warning("Trial expired email failed for %s: %s", to, err)
            else:
                user.trial_expired_email_sent = True
                processed += 1
            continue

    if processed:
        db.commit()
    return processed
