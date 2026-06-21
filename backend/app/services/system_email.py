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


def _valid_attachment_paths(paths: list[str] | None) -> list[str]:
    valid: list[str] = []
    for file_path in paths or []:
        if not file_path or not str(file_path).strip():
            continue
        path = Path(file_path)
        if path.is_file():
            valid.append(str(path))
    return valid


async def send_system_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    attachments: list[str] | None = None,
) -> tuple[bool, str | None]:
    """Deliver an app email to a user. Returns (success, error_message)."""
    if not _smtp_configured():
        msg = "App mail is not configured (SMTP_USER / SMTP_PASSWORD missing on the server)."
        logger.warning("System email skipped: %s subject=%s", msg, subject)
        return False, msg

    if not to:
        return False, "No recipient email address."

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

    for file_path in _valid_attachment_paths(attachments):
        path = Path(file_path)
        with open(path, "rb") as f:
            part = MIMEApplication(f.read(), Name=path.name)
        part["Content-Disposition"] = f'attachment; filename="{path.name}"'
        msg.attach(part)

    sender = settings.smtp_user.strip()
    use_ssl = settings.smtp_port == 465

    try:
        await aiosmtplib.send(
            msg,
            sender=sender,
            recipients=[to],
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            use_tls=use_ssl,
            start_tls=not use_ssl,
            timeout=60,
        )
        return True, None
    except Exception as exc:
        error = str(exc).strip() or exc.__class__.__name__
        logger.error("System email failed to %s: %s", to, error)
        hint = (
            " If you use Gmail/Google Workspace from a cloud server, try Amazon SES SMTP "
            "or an email API — Google often blocks SMTP login from datacenter IPs."
        )
        if "535" in error or "534" in error or "authentication" in error.lower():
            error = f"{error}. Check SMTP_USER/SMTP_PASSWORD (use an app password for Gmail).{hint}"
        elif "timeout" in error.lower() or "timed out" in error.lower():
            error = f"{error}. The mail server did not respond — verify SMTP_HOST/SMTP_PORT.{hint}"
        return False, error
