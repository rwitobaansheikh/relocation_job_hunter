"""SMTP-based email pattern generation and verification.

Python port of backend/email_finder_lib (patterns.js, verifier.js, index.js).
Generates likely corporate email addresses and checks them against the
company's MX server via RCPT TO — without sending any message (no DATA).
"""

from __future__ import annotations

import asyncio
import random
import re
import socket
import time
import unicodedata
from dataclasses import dataclass, field

import dns.resolver

DEFAULT_TIMEOUT_S = 10.0
DEFAULT_HELO = "verifier.local"
DEFAULT_DELAY_MS = 1500

GENERIC_LOCAL_PARTS = (
    "careers",
    "jobs",
    "talent",
    "recruiting",
    "recruitment",
    "hr",
    "hiring",
    "people",
    "hello",
)


@dataclass
class EmailCandidate:
    email: str
    pattern: str
    smtp_code: int | None = None
    status: str = "pending"  # accepted | rejected | greylisted | unknown | error
    error: str = ""


@dataclass
class FindEmailResult:
    domain: str
    mx_host: str = ""
    catch_all: bool = False
    best_guess: str | None = None
    note: str = ""
    candidates: list[EmailCandidate] = field(default_factory=list)


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFD", (name or "").strip().lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]", "", text)


def clean_domain(domain: str) -> str:
    text = (domain or "").strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"/.*$", "", text)
    return re.sub(r"^www\.", "", text)


def generate_patterns(first_name: str, last_name: str, domain: str) -> list[EmailCandidate]:
    if not first_name or not last_name or not domain:
        raise ValueError("first_name, last_name, and domain are all required")

    first = normalize_name(first_name)
    last = normalize_name(last_name)
    if not first or not last:
        raise ValueError("Could not normalize first/last name")

    clean = clean_domain(domain)
    f, l = first[0], last[0]

    raw = [
        ("first.last", f"{first}.{last}@{clean}"),
        ("flast", f"{f}{last}@{clean}"),
        ("firstlast", f"{first}{last}@{clean}"),
        ("first", f"{first}@{clean}"),
        ("firstl", f"{first}{l}@{clean}"),
        ("first_last", f"{first}_{last}@{clean}"),
        ("f.last", f"{f}.{last}@{clean}"),
        ("last.first", f"{last}.{first}@{clean}"),
        ("lastfirst", f"{last}{first}@{clean}"),
        ("last", f"{last}@{clean}"),
        ("lastf", f"{last}{f}@{clean}"),
        ("fl", f"{f}{l}@{clean}"),
    ]

    seen: set[str] = set()
    out: list[EmailCandidate] = []
    for pattern, email in raw:
        if email in seen:
            continue
        seen.add(email)
        out.append(EmailCandidate(email=email, pattern=pattern))
    return out


def classify_smtp_code(code: int) -> str:
    if code in (250, 251):
        return "accepted"
    if 550 <= code <= 553:
        return "rejected"
    if code in (450, 451, 452):
        return "greylisted"
    return "unknown"


def get_mx_host(domain: str) -> str:
    records = dns.resolver.resolve(domain, "MX")
    sorted_records = sorted(records, key=lambda r: r.preference)
    if not sorted_records:
        raise ValueError(f"No MX records found for {domain}")
    return str(sorted_records[0].exchange).rstrip(".")


def _read_smtp_response(sock: socket.socket, timeout_s: float) -> tuple[int, list[str]]:
    sock.settimeout(timeout_s)
    buffer = ""
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            raise TimeoutError("Connection closed while waiting for SMTP response")
        buffer += chunk.decode("utf-8", errors="replace")
        lines = [ln for ln in buffer.split("\r\n") if ln]
        if not lines:
            continue
        last = lines[-1]
        if re.match(r"^\d{3} ", last):
            return int(last[:3]), lines


def _smtp_probe(
    mx_host: str,
    *,
    helo_domain: str,
    mail_from: str,
    rcpt_to: str,
    timeout_s: float,
) -> int:
    sock = socket.create_connection((mx_host, 25), timeout=timeout_s)
    try:
        _read_smtp_response(sock, timeout_s)
        sock.sendall(f"EHLO {helo_domain}\r\n".encode())
        _read_smtp_response(sock, timeout_s)
        sock.sendall(f"MAIL FROM:<{mail_from}>\r\n".encode())
        _read_smtp_response(sock, timeout_s)
        sock.sendall(f"RCPT TO:<{rcpt_to}>\r\n".encode())
        code, _ = _read_smtp_response(sock, timeout_s)
        try:
            sock.sendall(b"QUIT\r\n")
        except OSError:
            pass
        return code
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _with_defaults(
    helo_domain: str | None,
    mail_from: str | None,
    timeout_ms: int | None,
) -> tuple[str, str, float]:
    helo = (helo_domain or DEFAULT_HELO).strip()
    mail = (mail_from or f"verify@{helo}").strip()
    timeout_s = (timeout_ms or int(DEFAULT_TIMEOUT_S * 1000)) / 1000.0
    return helo, mail, timeout_s


def check_catch_all(
    domain: str,
    *,
    helo_domain: str | None = None,
    mail_from: str | None = None,
    timeout_ms: int | None = None,
) -> tuple[str, bool]:
    helo, mail, timeout_s = _with_defaults(helo_domain, mail_from, timeout_ms)
    mx_host = get_mx_host(domain)
    probe_user = f"noexist-{int(time.time())}-{random.randint(0, 999999)}"
    try:
        code = _smtp_probe(
            mx_host,
            helo_domain=helo,
            mail_from=mail,
            rcpt_to=f"{probe_user}@{domain}",
            timeout_s=timeout_s,
        )
    except (TimeoutError, socket.timeout, OSError) as exc:
        raise RuntimeError(
            f"Connection to {mx_host}:25 failed — outbound port 25 may be blocked "
            f"on this network ({exc})"
        ) from exc
    return mx_host, classify_smtp_code(code) == "accepted"


def verify_email_address(
    email: str,
    mx_host: str,
    *,
    helo_domain: str | None = None,
    mail_from: str | None = None,
    timeout_ms: int | None = None,
) -> EmailCandidate:
    helo, mail, timeout_s = _with_defaults(helo_domain, mail_from, timeout_ms)
    local, _, domain = email.partition("@")
    pattern = local or "unknown"
    try:
        code = _smtp_probe(
            mx_host,
            helo_domain=helo,
            mail_from=mail,
            rcpt_to=email,
            timeout_s=timeout_s,
        )
        return EmailCandidate(
            email=email,
            pattern=pattern,
            smtp_code=code,
            status=classify_smtp_code(code),
        )
    except (TimeoutError, socket.timeout, OSError) as exc:
        return EmailCandidate(
            email=email,
            pattern=pattern,
            status="error",
            error=str(exc),
        )


def find_email_sync(
    first_name: str,
    last_name: str,
    domain: str,
    *,
    helo_domain: str | None = None,
    mail_from: str | None = None,
    timeout_ms: int | None = None,
    delay_ms: int | None = None,
) -> FindEmailResult:
    clean = clean_domain(domain)
    delay_s = (delay_ms if delay_ms is not None else DEFAULT_DELAY_MS) / 1000.0
    patterns = generate_patterns(first_name, last_name, clean)

    try:
        mx_host, is_catch_all = check_catch_all(
            clean,
            helo_domain=helo_domain,
            mail_from=mail_from,
            timeout_ms=timeout_ms,
        )
    except RuntimeError as exc:
        return FindEmailResult(
            domain=clean,
            note=str(exc),
            best_guess=patterns[0].email if patterns else None,
            candidates=patterns,
        )

    candidates: list[EmailCandidate] = []
    for item in patterns:
        verified = verify_email_address(
            item.email,
            mx_host,
            helo_domain=helo_domain,
            mail_from=mail_from,
            timeout_ms=timeout_ms,
        )
        verified.pattern = item.pattern
        candidates.append(verified)
        time.sleep(delay_s)

    if is_catch_all:
        return FindEmailResult(
            domain=clean,
            mx_host=mx_host,
            catch_all=True,
            best_guess=patterns[0].email if patterns else None,
            note=(
                "This domain accepts mail for any address, so SMTP cannot confirm which "
                "pattern is real. best_guess is the most common convention."
            ),
            candidates=candidates,
        )

    accepted = [c for c in candidates if c.status == "accepted"]
    return FindEmailResult(
        domain=clean,
        mx_host=mx_host,
        catch_all=False,
        best_guess=accepted[0].email if accepted else None,
        candidates=candidates,
    )


def find_generic_emails_sync(
    domain: str,
    *,
    helo_domain: str | None = None,
    mail_from: str | None = None,
    timeout_ms: int | None = None,
    delay_ms: int | None = None,
    limit: int = 5,
) -> FindEmailResult:
    """Verify common role-based inboxes (careers@, jobs@, etc.)."""
    clean = clean_domain(domain)
    delay_s = (delay_ms if delay_ms is not None else DEFAULT_DELAY_MS) / 1000.0
    patterns = [
        EmailCandidate(email=f"{local}@{clean}", pattern=local)
        for local in GENERIC_LOCAL_PARTS
    ]

    try:
        mx_host, is_catch_all = check_catch_all(
            clean,
            helo_domain=helo_domain,
            mail_from=mail_from,
            timeout_ms=timeout_ms,
        )
    except RuntimeError as exc:
        return FindEmailResult(
            domain=clean,
            note=str(exc),
            best_guess=patterns[0].email if patterns else None,
            candidates=patterns[:limit],
        )

    candidates: list[EmailCandidate] = []
    for item in patterns:
        if len(candidates) >= limit and not is_catch_all:
            break
        verified = verify_email_address(
            item.email,
            mx_host,
            helo_domain=helo_domain,
            mail_from=mail_from,
            timeout_ms=timeout_ms,
        )
        verified.pattern = item.pattern
        candidates.append(verified)
        if not is_catch_all and verified.status == "accepted" and len(
            [c for c in candidates if c.status == "accepted"]
        ) >= limit:
            break
        time.sleep(delay_s)

    if is_catch_all:
        return FindEmailResult(
            domain=clean,
            mx_host=mx_host,
            catch_all=True,
            best_guess=patterns[0].email if patterns else None,
            note="Catch-all domain — generic inbox is a best guess.",
            candidates=candidates,
        )

    accepted = [c for c in candidates if c.status == "accepted"]
    return FindEmailResult(
        domain=clean,
        mx_host=mx_host,
        catch_all=False,
        best_guess=accepted[0].email if accepted else None,
        candidates=candidates,
    )


async def find_email(
    first_name: str,
    last_name: str,
    domain: str,
    **kwargs,
) -> FindEmailResult:
    return await asyncio.to_thread(find_email_sync, first_name, last_name, domain, **kwargs)


async def find_generic_emails(domain: str, **kwargs) -> FindEmailResult:
    return await asyncio.to_thread(find_generic_emails_sync, domain, **kwargs)
