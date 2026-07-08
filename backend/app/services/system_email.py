"""Send transactional emails from the app's mailbox (email@jobapplicationflow.com)."""

import base64
import html as html_lib
import logging
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"


def system_from_header() -> str:
    """Formatted From header for all app → user emails."""
    addr = settings.system_email_from.strip()
    name = settings.system_email_name.strip()
    if name and addr:
        return f"{name} <{addr}>"
    return addr or settings.smtp_from or settings.smtp_user


def _smtp_configured() -> bool:
    return bool(settings.smtp_user and settings.smtp_password)


def _branded_html(body_html: str | None, body_text: str) -> str:
    """Wrap email content with the Job Application Flow logo header.

    Text-only emails are converted to simple HTML so they get the logo too."""
    logo_url = f"{settings.app_base_url.rstrip('/')}/logo-small.png"
    if not body_html:
        paragraphs = html_lib.escape(body_text).split("\n\n")
        body_html = "".join(
            f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip()
        )
    return (
        '<div style="max-width:560px;margin:0 auto;font-family:Arial,Helvetica,sans-serif;'
        'color:#26323c;">'
        '<div style="padding:20px 0;text-align:center;">'
        f'<img src="{logo_url}" alt="Job Application Flow" width="120" '
        'style="max-width:120px;height:auto;border:0;">'
        "</div>"
        f'<div style="padding:0 8px 24px;font-size:15px;line-height:1.55;">{body_html}</div>'
        "</div>"
    )


def _valid_attachment_paths(paths: list[str] | None) -> list[str]:
    valid: list[str] = []
    for file_path in paths or []:
        if not file_path or not str(file_path).strip():
            continue
        path = Path(file_path)
        if path.is_file():
            valid.append(str(path))
    return valid


async def _send_via_resend(
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None,
    attachments: list[str] | None,
) -> tuple[bool, str | None]:
    payload: dict = {
        "from": system_from_header(),
        "to": [to],
        "subject": subject,
        "text": body_text,
        "html": _branded_html(body_html, body_text),
    }
    files = []
    for file_path in _valid_attachment_paths(attachments):
        path = Path(file_path)
        files.append(
            {
                "filename": path.name,
                "content": base64.b64encode(path.read_bytes()).decode("ascii"),
            }
        )
    if files:
        payload["attachments"] = files

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _RESEND_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
        if resp.status_code in (200, 201):
            return True, None
        error = f"Resend API error {resp.status_code}: {resp.text[:300]}"
        logger.error("System email failed to %s: %s", to, error)
        return False, error
    except Exception as exc:
        error = str(exc).strip() or exc.__class__.__name__
        logger.error("System email failed to %s: %s", to, error)
        return False, error


async def send_system_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
    attachments: list[str] | None = None,
) -> tuple[bool, str | None]:
    """Deliver an app email to a user. Returns (success, error_message)."""
    if not to:
        return False, "No recipient email address."

    if settings.resend_api_key:
        return await _send_via_resend(to, subject, body_text, body_html, attachments)

    if not _smtp_configured():
        msg = "App mail is not configured (SMTP_USER / SMTP_PASSWORD missing on the server)."
        logger.warning("System email skipped: %s subject=%s", msg, subject)
        return False, msg

    msg = MIMEMultipart("mixed")
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body_text, "plain", "utf-8"))
    alt.attach(MIMEText(_branded_html(body_html, body_text), "html", "utf-8"))
    msg.attach(alt)

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
