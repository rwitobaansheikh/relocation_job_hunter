"""Email the loop owner when an automation run finishes, listing new jobs."""

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.database import AutomationLoop, AutomationRun, Job, JobApplication, User, UserProfile
from app.services.system_email import send_system_email

logger = logging.getLogger(__name__)

_TOP_JOBS_LIMIT = 5


def _applications_url() -> str:
    return f"{settings.app_base_url.rstrip('/')}/app/applications"


def _top_batch_jobs(db: Session, profile_id: int, batch_date: str) -> list[JobApplication]:
    return (
        db.query(JobApplication)
        .join(Job, Job.id == JobApplication.job_id)
        .filter(
            JobApplication.user_profile_id == profile_id,
            JobApplication.automation_batch_date == batch_date,
        )
        .order_by(JobApplication.ai_match_score.desc())
        .limit(_TOP_JOBS_LIMIT)
        .all()
    )


def build_run_summary_email(
    user: User,
    loop: AutomationLoop,
    run: AutomationRun,
    top_apps: list[JobApplication],
    batch_date: str,
) -> tuple[str, str, str, str]:
    """Return (to, subject, text, html) summarizing a finished automation run."""
    loop_name = loop.name or loop.role or f"loop {loop.id}"
    found = run.jobs_found or 0
    tailored = run.jobs_tailored or 0

    if found > 0:
        subject = f"{found} new job{'s' if found != 1 else ''} from your '{loop_name}' loop"
    else:
        subject = f"Your '{loop_name}' loop ran today — no new jobs matched"

    lines = [
        "Hi,",
        "",
        f"Your automation loop \"{loop_name}\" finished its daily run ({batch_date}).",
    ]
    html_parts = [
        "<p>Hi,</p>",
        f"<p>Your automation loop <strong>{loop_name}</strong> finished its daily run ({batch_date}).</p>",
    ]

    if found > 0:
        summary = f"{found} new job{'s' if found != 1 else ''} saved to your Applications"
        if tailored > 0:
            summary += f", {tailored} already tailored with a CV and cover letter"
        summary += "."
        lines += [summary, ""]
        html_parts.append(f"<p>{summary}</p>")

        if top_apps:
            lines.append("Top matches:")
            html_parts.append(
                '<p style="font-weight:700;margin-bottom:0.3rem">Top matches</p><ul>'
            )
            for app in top_apps:
                job = app.job
                meta = " · ".join(x for x in [job.company, job.location] if x)
                score = f" — Match {app.ai_match_score}/100" if app.ai_match_score else ""
                lines.append(f"  • {job.title} ({meta}){score}")
                html_parts.append(
                    f"<li><strong>{job.title}</strong> — {meta}{score}</li>"
                )
            lines.append("")
            html_parts.append("</ul>")

        lines.append(f"Review and apply: {_applications_url()}")
        html_parts.append(
            f'<p><a href="{_applications_url()}">Review your new jobs →</a></p>'
        )
    else:
        lines += [
            "No new jobs matched your filters today. The loop runs again tomorrow — "
            "consider widening the seniority levels or location if this keeps happening.",
            "",
            f"Adjust the loop: {settings.app_base_url.rstrip('/')}/app/automation",
        ]
        html_parts.append(
            "<p>No new jobs matched your filters today. The loop runs again tomorrow — "
            "consider widening the seniority levels or location if this keeps happening.</p>"
            f'<p><a href="{settings.app_base_url.rstrip("/")}/app/automation">Adjust the loop →</a></p>'
        )

    lines += ["", "— Job Application Flow"]
    html_parts.append("<p>— Job Application Flow</p>")
    return user.email, subject, "\n".join(lines), "".join(html_parts)


async def notify_run_complete(
    db: Session, loop: AutomationLoop, run: AutomationRun, batch_date: str
) -> bool:
    """Send the run-summary email to the loop's owner. Never raises."""
    try:
        profile = (
            db.query(UserProfile).filter(UserProfile.id == loop.user_profile_id).first()
        )
        user = (
            db.query(User).filter(User.id == profile.user_id).first() if profile else None
        )
        if not user or not user.email:
            return False

        top_apps = (
            _top_batch_jobs(db, loop.user_profile_id, batch_date)
            if (run.jobs_found or 0) > 0
            else []
        )
        to, subject, text, html = build_run_summary_email(
            user, loop, run, top_apps, batch_date
        )
        ok, err = await send_system_email(to, subject, text, html)
        if not ok:
            logger.warning("Automation run email failed for %s: %s", to, err)
        return ok
    except Exception as exc:
        logger.warning("Automation run notification failed for loop %s: %s", loop.id, exc)
        return False
