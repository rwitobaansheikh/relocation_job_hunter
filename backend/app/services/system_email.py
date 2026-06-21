"""Send transactional emails from the app's mailbox (email@jobapplicationflow.com)."""

import logging
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)


def system_from_header() -> str:
    """Formatted From header for all app → user emails."""
    addr = settings.system_email_from.strip()
    name = settings.system_email_name.strip()
    if name and addr:
        return f"{name} <{addr}>"
    return addr or settings.smtp_from or settings.smtp_user


def _smtp_configured() -> bool:
    return bool(settings.smtp_user and settings.smtp_password)


async def send_system_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    attachments: list[str] | None = None,
) -> bool:
    """Deliver an app email to a user. Returns False if SMTP is not configured."""
    if not _smtp_configured() or not to:
        logger.warning("System email skipped (SMTP not configured or no recipient): %s", subject)
        return False

    if body_html:
        msg = MIMEMultipart("mixed")
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body_text, "plain", "utf-8"))
        alt.attach(MIMEText(body_html, "html", "utf-8"))
        msg.attach(alt)
    else:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

    msg["Subject"] = subject
    msg["From"] = system_from_header()
    msg["To"] = to

    for file_path in attachments or []:
        path = Path(file_path)
        if path.exists():
            with open(path, "rb") as f:
                part = MIMEApplication(f.read(), Name=path.name)
            part["Content-Disposition"] = f'attachment; filename="{path.name}"'
            msg.attach(part)

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=True,
        )
        return True
    except Exception as exc:
        logger.error("System email failed to %s: %s", to, exc)
        return False
