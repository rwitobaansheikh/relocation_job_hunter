"""Send outreach emails with tailored documents."""

import logging
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib
from sqlalchemy.orm import Session

from app.config import settings
from app.database import ApplicationStatus, JobApplication, OutreachEmail
from app.services.email_finder import Contact, EmailFinder

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self) -> None:
        self.finder = EmailFinder()

    async def send_outreach(self, db: Session, application_id: int, dry_run: bool = False) -> list[OutreachEmail]:
        application = db.query(JobApplication).filter(JobApplication.id == application_id).first()
        if not application:
            raise ValueError(f"Application {application_id} not found")

        profile = application.user_profile
        job = application.job
        if not profile or not job:
            raise ValueError("Application missing profile or job")

        if not application.tailored_cv_path or not application.tailored_cover_letter_path:
            raise ValueError("Documents not tailored yet. Run tailor first.")

        contacts = await self.finder.find_contacts(
            company=job.company,
            domain=job.company_domain,
            job_title=job.title,
            limit=settings.max_emails_per_company,
        )

        results: list[OutreachEmail] = []
        for contact in contacts:
            subject = f"Application for {job.title} — {profile.full_name}"
            body = self._compose_email(profile, job, contact)

            outreach = OutreachEmail(
                application_id=application_id,
                recipient_name=contact.name,
                recipient_email=contact.email,
                recipient_title=contact.title,
                subject=subject,
                body=body,
                status="pending",
            )

            if dry_run:
                outreach.status = "dry_run"
            else:
                try:
                    await self._send_email(
                        to=contact.email,
                        subject=subject,
                        body=body,
                        attachments=[
                            application.tailored_cv_path,
                            application.tailored_cover_letter_path,
                        ],
                    )
                    outreach.status = "sent"
                    outreach.sent_at = datetime.utcnow()
                except Exception as exc:
                    outreach.status = "failed"
                    outreach.error_message = str(exc)
                    logger.error("Failed to send to %s: %s", contact.email, exc)

            db.add(outreach)
            results.append(outreach)

        if not dry_run and any(r.status == "sent" for r in results):
            application.status = ApplicationStatus.APPLIED.value
            application.applied_at = datetime.utcnow()

        db.commit()
        return results

    def _compose_email(self, profile, job, contact: Contact) -> str:
        greeting = f"Dear {contact.name}," if contact.name else "Dear Hiring Team,"
        return f"""{greeting}

I am writing to express my strong interest in the {job.title} position at {job.company}. 
I am currently based in {profile.location or 'abroad'} and am actively seeking opportunities 
that offer relocation support.

I believe my background in {profile.skills or 'software development'} aligns well with your 
requirements, and I am particularly drawn to {job.company}'s work in this space.

Please find my tailored CV and cover letter attached. I would welcome the opportunity to 
discuss how I can contribute to your team.

Thank you for your consideration.

Best regards,
{profile.full_name}
{profile.email}
{profile.phone}
{profile.linkedin_url}
"""

    async def _send_email(self, to: str, subject: str, body: str, attachments: list[str]) -> None:
        if not settings.smtp_user or not settings.smtp_password:
            raise ValueError("SMTP credentials not configured")

        msg = MIMEMultipart()
        msg["From"] = settings.smtp_from or settings.smtp_user
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        for file_path in attachments:
            path = Path(file_path)
            if path.exists():
                with open(path, "rb") as f:
                    part = MIMEApplication(f.read(), Name=path.name)
                part["Content-Disposition"] = f'attachment; filename="{path.name}"'
                msg.attach(part)

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
