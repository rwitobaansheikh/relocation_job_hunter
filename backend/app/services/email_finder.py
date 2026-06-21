"""Find hiring manager and company outreach emails via OSINT + SMTP verification."""

import logging
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services import rate_limiter
from app.services.smtp_email_verifier import (
    find_email,
    find_generic_emails,
    generate_patterns,
    normalize_name,
)

logger = logging.getLogger(__name__)


@dataclass
class Contact:
    name: str
    email: str
    title: str
    confidence: int = 0
    pattern: str = ""
    verification_status: str = ""
    catch_all: bool = False


class EmailFinder:
    rocketreach_base = "https://api.rocketreach.co/api/v2"

    async def find_contacts(self, company: str, domain: str, job_title: str, limit: int = 5) -> list[Contact]:
        domain = self._normalize_domain(domain, company)
        if not domain:
            return []

        contacts: list[Contact] = []
        seen_emails: set[str] = set()

        if settings.rocketreach_api_key:
            for contact in await self._search_rocketreach(company, domain, limit):
                if contact.email and contact.email.lower() not in seen_emails:
                    seen_emails.add(contact.email.lower())
                    contacts.append(contact)

        if len(contacts) < limit:
            for contact in await self._search_osint_verified(company, domain, job_title, limit - len(contacts)):
                key = contact.email.lower()
                if contact.email and key not in seen_emails:
                    seen_emails.add(key)
                    contacts.append(contact)

        if len(contacts) < limit:
            for contact in await self._find_generic_verified(domain, limit - len(contacts)):
                key = contact.email.lower()
                if contact.email and key not in seen_emails:
                    seen_emails.add(key)
                    contacts.append(contact)

        if not contacts:
            logger.info("No verified contacts for %s — using unverified generic fallbacks", domain)
            for contact in self._fallback_contacts(company, domain, limit):
                key = contact.email.lower()
                if key not in seen_emails:
                    seen_emails.add(key)
                    contacts.append(contact)

        contacts.sort(key=lambda c: c.confidence, reverse=True)
        return contacts[:limit]

    def _verify_options(self) -> dict:
        return {
            "helo_domain": settings.smtp_verify_helo_domain or None,
            "mail_from": settings.smtp_verify_mail_from or None,
            "timeout_ms": settings.smtp_verify_timeout_ms,
            "delay_ms": settings.smtp_verify_delay_ms,
        }

    async def _verify_person(self, name: str, title: str, domain: str) -> Contact | None:
        parts = [p for p in re.sub(r"[^a-zA-Z\s'-]", " ", name).split() if p]
        if len(parts) < 2:
            return None

        first, last = parts[0], parts[-1]
        if not settings.smtp_verify_enabled:
            email = f"{normalize_name(first)}.{normalize_name(last)}@{domain}"
            return Contact(
                name=name,
                email=email,
                title=title,
                confidence=40,
                pattern="first.last",
                verification_status="guess",
            )

        await rate_limiter.acquire("smtp_verify")
        try:
            result = await find_email(first, last, domain, **self._verify_options())
        except Exception as exc:
            logger.warning("SMTP verify failed for %s at %s: %s", name, domain, exc)
            email = f"{normalize_name(first)}.{normalize_name(last)}@{domain}"
            return Contact(
                name=name,
                email=email,
                title=title,
                confidence=35,
                pattern="first.last",
                verification_status="error",
            )

        if result.note and not result.mx_host:
            patterns = generate_patterns(first, last, domain)
            email = patterns[0].email if patterns else f"{normalize_name(first)}.{normalize_name(last)}@{domain}"
            return Contact(
                name=name,
                email=email,
                title=title,
                confidence=35,
                pattern="first.last",
                verification_status="guess",
            )

        best = result.best_guess
        if not best:
            return None

        accepted = next((c for c in result.candidates if c.email == best), None)
        pattern = accepted.pattern if accepted else "first.last"
        status = accepted.status if accepted else ("guess" if result.catch_all else "unknown")

        if result.catch_all:
            confidence = 55
        elif status == "accepted":
            confidence = 92
        else:
            confidence = 45

        return Contact(
            name=name,
            email=best,
            title=title,
            confidence=confidence,
            pattern=pattern,
            verification_status="catch_all" if result.catch_all else status,
            catch_all=result.catch_all,
        )

    async def _search_osint_verified(
        self, company: str, domain: str, job_title: str, limit: int
    ) -> list[Contact]:
        raw = await self._search_osint(company, domain, limit * 2)
        contacts: list[Contact] = []
        for person in raw:
            if len(contacts) >= limit:
                break
            verified = await self._verify_person(person.name, person.title, domain)
            if verified:
                contacts.append(verified)
        return contacts

    async def _find_generic_verified(self, domain: str, limit: int) -> list[Contact]:
        if limit <= 0:
            return []

        if not settings.smtp_verify_enabled:
            return [
                Contact(name="HR Team", email=f"careers@{domain}", title="Human Resources", confidence=30, verification_status="guess"),
                Contact(name="Recruiting", email=f"jobs@{domain}", title="Recruiting", confidence=28, verification_status="guess"),
            ][:limit]

        await rate_limiter.acquire("smtp_verify")
        try:
            result = await find_generic_emails(domain, limit=limit, **self._verify_options())
        except Exception as exc:
            logger.warning("Generic SMTP verify failed for %s: %s", domain, exc)
            return self._fallback_contacts("", domain, limit)

        if result.note and not result.mx_host:
            return self._fallback_contacts("", domain, limit)

        labels = {
            "careers": ("HR Team", "Human Resources"),
            "jobs": ("Recruiting", "Recruiting"),
            "talent": ("Talent", "Talent Acquisition"),
            "recruiting": ("Recruiting", "Recruiting"),
            "recruitment": ("Recruitment", "Recruitment"),
            "hr": ("HR Team", "Human Resources"),
            "hiring": ("Hiring Team", "Hiring"),
            "people": ("People Team", "People Operations"),
            "hello": ("Team", "General"),
        }

        contacts: list[Contact] = []
        for candidate in result.candidates:
            if candidate.status not in ("accepted",) and not result.catch_all:
                continue
            if not candidate.email:
                continue
            local = candidate.pattern or candidate.email.split("@")[0]
            name, title = labels.get(local, ("Hiring Team", "Recruiting"))
            if result.catch_all:
                confidence = 50
                status = "catch_all"
            elif candidate.status == "accepted":
                confidence = 78
                status = "accepted"
            else:
                continue
            contacts.append(
                Contact(
                    name=name,
                    email=candidate.email,
                    title=title,
                    confidence=confidence,
                    pattern=local,
                    verification_status=status,
                    catch_all=result.catch_all,
                )
            )
            if len(contacts) >= limit:
                break

        if not contacts and result.catch_all and result.best_guess:
            local = result.best_guess.split("@")[0]
            name, title = labels.get(local, ("Hiring Team", "Recruiting"))
            contacts.append(
                Contact(
                    name=name,
                    email=result.best_guess,
                    title=title,
                    confidence=45,
                    pattern=local,
                    verification_status="catch_all",
                    catch_all=True,
                )
            )
        return contacts

    async def _search_rocketreach(self, company: str, domain: str, limit: int) -> list[Contact]:
        contacts: list[Contact] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            search_url = f"{self.rocketreach_base}/person/search"
            headers = {
                "Api-Key": settings.rocketreach_api_key,
                "Content-Type": "application/json",
            }

            payload = {
                "query": {
                    "current_employer": [domain, company],
                    "current_title": ["hr", "human resources", "recruiter", "talent acquisition", "hiring"],
                }
            }

            try:
                await rate_limiter.acquire("rocketreach")
                response = await client.post(search_url, json=payload, headers=headers)
                if response.status_code == 401:
                    logger.error("RocketReach API Key is unauthorized (401).")
                    return []
                response.raise_for_status()
                data = response.json()
                profiles = data.get("profiles", data) if isinstance(data, dict) else data
                if not isinstance(profiles, list):
                    profiles = []
            except Exception as exc:
                logger.error("RocketReach person search failed for %s: %s", domain, exc)
                return []

            seen_emails: set[str] = set()
            for profile in profiles:
                if len(contacts) >= limit:
                    break
                person_id = profile.get("id")
                if not person_id:
                    continue
                try:
                    await rate_limiter.acquire("rocketreach")
                    lookup_url = f"{self.rocketreach_base}/person/lookup"
                    lookup_resp = await client.get(lookup_url, params={"id": person_id}, headers=headers)
                    lookup_resp.raise_for_status()
                    person_data = lookup_resp.json()

                    emails = person_data.get("emails", [])
                    name = person_data.get("name") or profile.get("name") or "Hiring Team"
                    title = person_data.get("current_title") or profile.get("current_title") or "Recruiter"

                    best_email = None
                    for e in emails:
                        is_valid = str(e.get("valid", "")).lower() == "true" or str(e.get("smtp_valid", "")).lower() == "valid"
                        if e.get("type") == "professional" and is_valid:
                            best_email = e.get("email")
                            break
                    if not best_email and emails:
                        for e in emails:
                            if e.get("type") == "professional":
                                best_email = e.get("email")
                                break
                        if not best_email:
                            best_email = emails[0].get("email")

                    if best_email and best_email not in seen_emails:
                        seen_emails.add(best_email)
                        contacts.append(
                            Contact(
                                name=name,
                                email=best_email,
                                title=title,
                                confidence=90,
                                verification_status="accepted",
                            )
                        )
                except Exception as exc:
                    logger.warning("RocketReach lookup failed for ID %s: %s", person_id, exc)

        return contacts

    async def _search_osint(self, company: str, domain: str, limit: int) -> list[Contact]:
        contacts: list[Contact] = []
        seen_names: set[str] = set()

        queries = [
            f'site:linkedin.com/in/ "HR" "{company}"',
            f'site:linkedin.com/in/ "Recruiter" "{company}"',
            f'site:linkedin.com/in/ "Talent Acquisition" "{company}"',
        ]

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            for query in queries:
                if len(contacts) >= limit:
                    break

                try:
                    res = await client.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers)
                    if res.status_code != 200:
                        continue

                    soup = BeautifulSoup(res.text, "html.parser")
                    results = soup.select(".result__body")

                    for r in results:
                        if len(contacts) >= limit:
                            break

                        title_el = r.select_one(".result__title a")
                        if not title_el:
                            continue

                        title_text = title_el.get_text(strip=True)
                        title_text = re.sub(r"\s*\|\s*LinkedIn.*$", "", title_text, flags=re.IGNORECASE)

                        parts = [p.strip() for p in title_text.split("-")]
                        if not parts:
                            continue

                        name = parts[0].strip()
                        job_title = parts[1].strip() if len(parts) > 1 else "Recruiter"

                        if len(name.split()) > 4 or any(
                            keyword in name.lower() for keyword in ["jobs", "careers", "hiring", "recruiting"]
                        ):
                            continue

                        key = name.lower()
                        if key in seen_names:
                            continue
                        seen_names.add(key)
                        contacts.append(Contact(name=name, email="", title=job_title, confidence=0))

                except Exception as exc:
                    logger.warning("OSINT search failed for query '%s': %s", query, exc)

        return contacts

    @staticmethod
    def _normalize_domain(domain: str, company: str) -> str:
        if domain and "." in domain:
            return domain.lower().strip()
        if company:
            clean = company.lower().replace(" ", "").replace(",", "").replace(".", "")
            return f"{clean}.com"
        return ""

    @staticmethod
    def _fallback_contacts(company: str, domain: str, limit: int) -> list[Contact]:
        domain = domain or f"{company.lower().replace(' ', '')}.com"
        return [
            Contact(name="HR Team", email=f"careers@{domain}", title="Human Resources", confidence=25, verification_status="guess"),
            Contact(name="Recruiting", email=f"jobs@{domain}", title="Recruiting", confidence=23, verification_status="guess"),
            Contact(name="Talent", email=f"talent@{domain}", title="Talent Acquisition", confidence=21, verification_status="guess"),
        ][:limit]
