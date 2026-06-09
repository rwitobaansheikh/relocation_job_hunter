"""Send outreach emails with tailored documents."""

import json
import logging
import re
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import ApplicationStatus, JobApplication, OutreachEmail, UserProfile
from app.security import decrypt_secret
from app.services.email_finder import Contact, EmailFinder
from app.services.llm import llm_generate

logger = logging.getLogger(__name__)

# Hunter sometimes only yields a generic mailbox (careers@, jobs@) for which we
# synthesize a placeholder "name". These are NOT real people, so we must greet
# them as a team rather than "Dear Recruiting,".
_GENERIC_NAMES = {
    "hr team",
    "recruiting",
    "talent",
    "hiring team",
    "human resources",
    "talent acquisition",
}

# Any "[ ... ]" token (e.g. "[Recipient Name]", "[Company]") that survives in
# the final copy is an LLM placeholder leak and must never reach a recipient.
_PLACEHOLDER_RE = re.compile(r"\[[^\]\n]{1,80}\]")

EMAIL_SYSTEM = (
    "Act as an expert career coach and professional copywriter specializing in cold "
    "outreach for job seekers. You write highly tailored, compelling, concise outreach "
    "emails to hiring managers and recruiters. Every email must feel personal, authentic, "
    "and unique to the recipient - never a generic copy-paste template."
)


class EmailService:
    def __init__(self) -> None:
        self.finder = EmailFinder()

    @staticmethod
    def _registered_email(profile) -> str:
        """Inbox tied to the user's login — used for test sends, not SMTP identity."""
        user = getattr(profile, "user", None)
        if user and getattr(user, "email", None):
            return user.email.strip()
        return (getattr(profile, "email", None) or "").strip()

    async def send_outreach(
        self,
        db: Session,
        application_id: int,
        dry_run: bool = False,
        test_to_self: bool = False,
        max_recipients: int | None = None,
    ) -> list[OutreachEmail]:
        application = (
            db.query(JobApplication)
            .options(joinedload(JobApplication.user_profile).joinedload(UserProfile.user))
            .filter(JobApplication.id == application_id)
            .first()
        )
        if not application:
            raise ValueError(f"Application {application_id} not found")

        profile = application.user_profile
        job = application.job
        if not profile or not job:
            raise ValueError("Application missing profile or job")

        if not application.tailored_cv_path:
            raise ValueError("Documents not tailored yet. Run tailor first.")

        contacts = await self.finder.find_contacts(
            company=job.company,
            domain=job.company_domain,
            job_title=job.title,
            limit=settings.max_emails_per_company,
        )
        # Automation passes a per-company cap so a single send can't exceed the
        # user's per-domain limit.
        if max_recipients is not None:
            contacts = contacts[: max(0, max_recipients)]

        background = self._build_background(profile, application)
        smtp = self._smtp_config(profile)

        # Test mode: actually deliver one real email to the user's own inbox
        # (with attachments) so SMTP can be verified end-to-end, without
        # contacting the real recipients.
        if test_to_self:
            return [
                await self._send_test_to_self(
                    db, application, profile, job, contacts, background, smtp
                )
            ]

        results: list[OutreachEmail] = []
        for contact in contacts:
            subject, body = await self._generate_email(profile, job, contact, background)

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
                        smtp=smtp,
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

    async def _send_test_to_self(
        self,
        db: Session,
        application,
        profile,
        job,
        contacts: list[Contact],
        background: str,
        smtp: dict | None = None,
    ) -> OutreachEmail:
        smtp = smtp or self._smtp_config(profile)
        self_address = self._registered_email(profile)
        if not self_address:
            raise ValueError(
                "No registered account email found. Log in with a valid email address."
            )

        primary = contacts[0] if contacts else Contact(name="Hiring Team", email="", title="")
        intended = ", ".join(f"{c.name} <{c.email}>".strip() for c in contacts) or "(no contacts found)"
        real_subject, real_body = await self._generate_email(profile, job, primary, background)
        subject = f"[TEST] {real_subject}"
        body = (
            "*** THIS IS A TEST EMAIL SENT TO YOURSELF ***\n"
            f"In a real send, this outreach would go to: {intended}\n"
            f"Company: {job.company}\n"
            f"Subject would be: {real_subject}\n"
            "----------------------------------------------------------\n\n"
            + real_body
        )

        outreach = OutreachEmail(
            application_id=application.id,
            recipient_name="Me (test send)",
            recipient_email=self_address,
            recipient_title="SMTP test",
            subject=subject,
            body=body,
            status="pending",
        )
        try:
            await self._send_email(
                to=self_address,
                subject=subject,
                body=body,
                attachments=[
                    application.tailored_cv_path,
                    application.tailored_cover_letter_path,
                ],
                smtp=smtp,
            )
            outreach.status = "test_sent"
            outreach.sent_at = datetime.utcnow()
        except Exception as exc:
            outreach.status = "failed"
            outreach.error_message = str(exc)
            logger.error("Test send to %s failed: %s", self_address, exc)

        db.add(outreach)
        db.commit()
        db.refresh(outreach)
        return outreach

    def _build_background(self, profile, application) -> str:
        """Assemble the candidate's background (CV summary + cover-letter core
        value) used to craft the outreach hook."""
        cover_value = ""
        if application is not None and application.analysis_json:
            try:
                cover_value = (json.loads(application.analysis_json).get("cover_letter") or "").strip()
            except (ValueError, TypeError):
                cover_value = ""
        if not cover_value:
            cover_value = (profile.baseline_cover_letter_text or "")[:1500]

        parts = [
            f"Candidate name: {profile.full_name}",
            f"Current location: {profile.location or 'N/A'}",
            f"Key skills: {profile.skills or 'N/A'}",
            f"Professional summary: {profile.summary or 'N/A'}",
            f"CV details: {(profile.cv_text or '')[:3000]}",
            f"Cover letter core value: {cover_value[:1500]}",
        ]
        return "\n".join(parts)

    async def _generate_email(self, profile, job, contact: Contact, background: str) -> tuple[str, str]:
        """Generate a tailored (subject, body) for a single recipient. Falls back
        to a simple deterministic email if the AI is unavailable or leaks
        unresolved "[placeholder]" tokens into the copy."""
        recipient = f"{contact.name or 'Hiring Team'}{f', {contact.title}' if contact.title else ''}"
        greeting = self._greeting(contact, job)
        prompt = f"""Write a highly tailored, compelling, concise cold outreach email to this recipient.
Find the single best "hook" connecting the candidate's experience to the company.

### CONTEXT & INPUTS:
1. Target Company: {job.company}
2. Recipient Name & Role: {recipient}
3. Job Title I'm targeting: {job.title}
4. Recipient Context/Hook (optional): {(job.description or '')[:600]}

MY BACKGROUND:
{background}

### EMAIL GUIDELINES:
- Open the email body with EXACTLY this greeting line, verbatim, then a blank line: {greeting}
- Subject Line: high-open, professional, slightly intriguing. Avoid generic "Job Application: {profile.full_name}".
- Length: short and punchy (UNDER 150 words). Keep paragraphs to 1-2 sentences (read on phones).
- Tone: professional yet warm, confident but humble; adapt to the company's culture.
- The "Why You": mention a specific, genuine reason you respect the company or recipient's work.
- The "Why Me": highlight exactly ONE major achievement from the CV that solves a problem they likely have.
- Call to Action: low-friction. Don't ask for a 30-minute interview; ask for a brief 5-minute chat or point them to the attached CV and cover letter.
- Sign off with the candidate's name. Then on separate lines add: {profile.email}{f' | {profile.phone}' if profile.phone else ''}{f' | {profile.linkedin_url}' if profile.linkedin_url else ''}
- Do NOT mention anything about tailoring, customizing, or adjusting the CV or cover letter.
- CRITICAL: Write real, final content only. NEVER output square-bracket placeholders such as [Name], [Recipient Name], [Company], [Your Name], or [Position]. Use the actual values given above.

### OUTPUT FORMAT (exactly this, no labels, no markdown):
First line: the subject line only.
Then a blank line, then the email body."""

        raw = await llm_generate(prompt, system=EMAIL_SYSTEM, temperature=0.8, max_tokens=1024)
        subject, body = self._parse_email(raw)
        subject = self._sanitize_copy(subject, profile, job, contact)
        body = self._sanitize_copy(body, profile, job, contact)
        # If the model still leaked a placeholder we could not resolve, or
        # produced nothing usable, fall back to the deterministic template which
        # is guaranteed to be placeholder-free.
        if (
            not subject
            or not body
            or _PLACEHOLDER_RE.search(subject)
            or _PLACEHOLDER_RE.search(body)
        ):
            logger.warning(
                "Email for %s contained unresolved placeholders or was empty; using fallback.",
                contact.email or contact.name,
            )
            return self._fallback_email(profile, job, contact)
        return subject, body

    @staticmethod
    def _greeting(contact: Contact, job) -> str:
        """A concrete greeting line - never a bracketed placeholder. Real people
        are greeted by first name; generic mailboxes get a team greeting."""
        name = (contact.name or "").strip()
        if name and name.lower() not in _GENERIC_NAMES:
            first = name.split()[0]
            return f"Dear {first},"
        return f"Dear Hiring Team at {job.company},"

    def _sanitize_copy(self, text: str, profile, job, contact: Contact) -> str:
        """Replace any bracketed placeholder tokens the model may have emitted
        with the real values we already know. Anything still bracketed after
        this is treated as a failure by the caller."""
        if not text:
            return text
        name = (contact.name or "").strip()
        if name and name.lower() not in _GENERIC_NAMES:
            recipient_name = name.split()[0]
        else:
            recipient_name = "Hiring Team"
        # Order matters: resolve sender-specific tokens (e.g. "[Your Name]")
        # BEFORE the generic recipient-name rule, otherwise a sender placeholder
        # would wrongly be filled with the recipient's name.
        substitutions = [
            (r"\[[^\]]*\b(?:your[\s_-]*name|sender|my[\s_-]*name|candidate)\b[^\]]*\]", profile.full_name or ""),
            (r"\[[^\]]*\b(?:e-?mail)\b[^\]]*\]", profile.email or ""),
            (r"\[[^\]]*\b(?:phone|telephone|number)\b[^\]]*\]", profile.phone or ""),
            (r"\[[^\]]*\blinkedin\b[^\]]*\]", profile.linkedin_url or ""),
            (r"\[[^\]]*\bcompany\b[^\]]*\]", job.company or ""),
            (r"\[[^\]]*\b(?:job[\s_-]*title|position|role|title)\b[^\]]*\]", job.title or ""),
            (r"\[[^\]]*\b(?:recipient|hiring manager|first[\s_-]*name|full[\s_-]*name|name)\b[^\]]*\]", recipient_name),
        ]
        for pattern, repl in substitutions:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        return text.strip()

    @staticmethod
    def _parse_email(raw: str) -> tuple[str, str]:
        """Split the model output into (subject, body). First non-empty line is
        the subject; the rest is the body."""
        if not raw or not raw.strip():
            return "", ""
        lines = raw.strip().splitlines()
        idx = 0
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
        if idx >= len(lines):
            return "", ""
        subject = lines[idx].strip()
        # Drop a leading "Subject:" label and surrounding brackets if present.
        subject = subject.lstrip("[").rstrip("]").strip()
        if subject.lower().startswith("subject:"):
            subject = subject[len("subject:"):].strip()
        body = "\n".join(lines[idx + 1:]).strip()
        return subject, body

    def _fallback_email(self, profile, job, contact: Contact) -> tuple[str, str]:
        greeting = self._greeting(contact, job)
        subject = f"{job.title} — a quick note from {profile.full_name}"
        body = f"""{greeting}

I'm reaching out because I admire the work {job.company} is doing and I'd love to contribute as a {job.title}.

My background in {profile.skills or 'software development'} maps closely to what the role needs, and I'm confident I could add value to your team quickly.

Would you be open to a brief 5-minute chat? My CV and cover letter are attached for the details.

Best regards,
{profile.full_name}
{profile.email}{f' | {profile.phone}' if profile.phone else ''}{f' | {profile.linkedin_url}' if profile.linkedin_url else ''}
"""
        return subject, body

    @staticmethod
    def _smtp_config(profile) -> dict:
        """Resolve the sending identity: the user's own SMTP credentials when
        configured (hybrid model), otherwise the shared app-level credentials."""
        password = decrypt_secret(getattr(profile, "smtp_password_enc", "") or "")
        if getattr(profile, "smtp_user", "") and password:
            host = profile.smtp_host or settings.smtp_host
            user = profile.smtp_user
            return {
                "host": host,
                "port": profile.smtp_port or settings.smtp_port,
                "user": user,
                "password": password,
                "from": profile.smtp_from or user,
            }
        # Fall back to the shared, app-level mailbox.
        return {
            "host": settings.smtp_host,
            "port": settings.smtp_port,
            "user": settings.smtp_user,
            "password": settings.smtp_password,
            "from": settings.smtp_from or settings.smtp_user,
        }

    async def send_system_email(self, to: str, subject: str, body: str) -> None:
        """Send a plain notification from the shared app mailbox (used for
        contact-us messages). Raises ValueError if no shared SMTP is set."""
        smtp = {
            "host": settings.smtp_host,
            "port": settings.smtp_port,
            "user": settings.smtp_user,
            "password": settings.smtp_password,
            "from": settings.smtp_from or settings.smtp_user,
        }
        await self._send_email(to, subject, body, [], smtp)

    async def _send_email(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: list[str],
        smtp: dict,
    ) -> None:
        if not smtp.get("user") or not smtp.get("password"):
            raise ValueError(
                "No sending identity configured. Add your SMTP credentials in Settings."
            )

        msg = MIMEMultipart()
        msg["From"] = smtp["from"] or smtp["user"]
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
            hostname=smtp["host"],
            port=smtp["port"],
            username=smtp["user"],
            password=smtp["password"],
            start_tls=True,
        )
