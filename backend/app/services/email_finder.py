"""Find hiring manager and company outreach emails via website scrape, search, and SMTP."""

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
    smtp_port25_available,
)
from app.services.company_domain_resolver import (
    clean_domain,
    is_job_board_host,
    slug_domain_guess,
)
from app.services.website_email_scraper import WebsiteEmailScraper

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

    def __init__(self) -> None:
        self._website = WebsiteEmailScraper()
        self._smtp_available: bool | None = None

    def _can_smtp_verify(self) -> bool:
        if not settings.smtp_verify_enabled:
            return False
        if self._smtp_available is None:
            self._smtp_available = smtp_port25_available()
        return self._smtp_available

    async def find_contacts(self, company: str, domain: str, job_title: str, limit: int = 5) -> list[Contact]:
        domain = self._normalize_domain(domain, company)
        if not domain:
            return []

        contacts: list[Contact] = []
        seen_emails: set[str] = set()

        scraped = await self._website.find_emails(company, domain, limit=limit * 2)
        for item in scraped:
            key = item.email.lower()
            if key in seen_emails:
                continue
            seen_emails.add(key)
            contacts.append(
                Contact(
                    name=item.name,
                    email=item.email,
                    title=item.title,
                    confidence=item.confidence,
                    pattern=item.email.split("@")[0],
                    verification_status=item.verification_status,
                )
            )

        if settings.rocketreach_api_key and len(contacts) < limit:
            for contact in await self._search_rocketreach(company, domain, limit - len(contacts)):
                key = contact.email.lower()
                if contact.email and key not in seen_emails:
                    seen_emails.add(key)
                    contacts.append(contact)

        scraped_set = {c.email.lower() for c in contacts}

        if len(contacts) < limit:
            for contact in await self._search_osint_verified(
                company, domain, job_title, scraped_set, limit - len(contacts)
            ):
                key = contact.email.lower()
                if contact.email and key not in seen_emails:
                    seen_emails.add(key)
                    contacts.append(contact)

        if len(contacts) < limit and self._can_smtp_verify():
            for contact in await self._find_generic_verified(domain, limit - len(contacts)):
                key = contact.email.lower()
                if contact.email and key not in seen_emails:
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

    def _pattern_match_on_site(
        self, first: str, last: str, domain: str, known: set[str]
    ) -> Contact | None:
        for candidate in generate_patterns(first, last, domain):
            if candidate.email.lower() in known:
                return Contact(
                    name=f"{first} {last}".strip(),
                    email=candidate.email,
                    title="Recruiter",
                    confidence=85,
                    pattern=candidate.pattern,
                    verification_status="found_on_site",
                )
        return None

    async def _verify_person(
        self, name: str, title: str, domain: str, known: set[str]
    ) -> Contact | None:
        parts = [p for p in re.sub(r"[^a-zA-Z\s'-]", " ", name).split() if p]
        if len(parts) < 2:
            return None

        first, last = parts[0], parts[-1]
        on_site = self._pattern_match_on_site(first, last, domain, known)
        if on_site:
            on_site.title = title or on_site.title
            return on_site

        if not self._can_smtp_verify():
            email = f"{normalize_name(first)}.{normalize_name(last)}@{domain}"
            return Contact(
                name=name,
                email=email,
                title=title,
                confidence=48,
                pattern="first.last",
                verification_status="pattern_guess",
            )

        await rate_limiter.acquire("smtp_verify")
        try:
            result = await find_email(first, last, domain, **self._verify_options())
        except Exception as exc:
            logger.warning("SMTP verify failed for %s at %s: %s", name, domain, exc)
            return None

        if result.note and not result.mx_host:
            return None

        best = result.best_guess
        if not best:
            return None

        accepted = next((c for c in result.candidates if c.email == best), None)
        pattern = accepted.pattern if accepted else "first.last"
        status = accepted.status if accepted else ("pattern_guess" if result.catch_all else "unknown")

        if result.catch_all:
            confidence = 58
        elif status == "accepted":
            confidence = 92
        else:
            return None

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
        self,
        company: str,
        domain: str,
        job_title: str,
        known: set[str],
        limit: int,
    ) -> list[Contact]:
        raw = await self._search_osint(company, domain, limit * 3)
        contacts: list[Contact] = []
        for person in raw:
            if len(contacts) >= limit:
                break
            verified = await self._verify_person(person.name, person.title, domain, known)
            if verified:
                contacts.append(verified)
        return contacts

    async def _find_generic_verified(self, domain: str, limit: int) -> list[Contact]:
        if limit <= 0:
            return []

        await rate_limiter.acquire("smtp_verify")
        try:
            result = await find_generic_emails(domain, limit=limit, **self._verify_options())
        except Exception as exc:
            logger.warning("Generic SMTP verify failed for %s: %s", domain, exc)
            return []

        if result.note and not result.mx_host:
            return []

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
                confidence = 52
                status = "catch_all"
            elif candidate.status == "accepted":
                confidence = 80
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
            f'site:linkedin.com/in/ recruiter "{company}"',
            f'site:linkedin.com/in/ "talent acquisition" "{company}"',
            f'site:linkedin.com/in/ "human resources" "{company}"',
            f'"{company}" recruiter {domain}',
        ]

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for query in queries:
                if len(contacts) >= limit:
                    break

                for fetch in (
                    lambda q=query: client.get("https://html.duckduckgo.com/html/", params={"q": q}, headers=headers),
                    lambda q=query: client.post(
                        "https://html.duckduckgo.com/html/",
                        data={"q": q, "kl": "us-en"},
                        headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                    ),
                ):
                    try:
                        res = await fetch()
                        if res.status_code != 200:
                            continue

                        parsed = self._parse_search_people(res.text)
                        for name, job_title in parsed:
                            if len(contacts) >= limit:
                                break
                            key = name.lower()
                            if key in seen_names:
                                continue
                            seen_names.add(key)
                            contacts.append(Contact(name=name, email="", title=job_title, confidence=0))
                    except Exception as exc:
                        logger.debug("OSINT search failed for '%s': %s", query, exc)

        return contacts

    @staticmethod
    def _parse_search_people(html: str) -> list[tuple[str, str]]:
        soup = BeautifulSoup(html, "html.parser")
        people: list[tuple[str, str]] = []
        seen: set[str] = set()

        link_selectors = (
            "a.result__a",
            ".result__title a",
            "h2 a",
            "a[href*='linkedin.com/in/']",
        )
        links = []
        for sel in link_selectors:
            links.extend(soup.select(sel))

        for link in links:
            href = link.get("href", "")
            title_text = link.get_text(strip=True)
            if "linkedin.com/in/" not in href and "linkedin" not in title_text.lower():
                continue

            title_text = re.sub(r"\s*\|\s*LinkedIn.*$", "", title_text, flags=re.IGNORECASE)
            title_text = re.sub(r"\s*-\s*LinkedIn.*$", "", title_text, flags=re.IGNORECASE)
            parts = re.split(r"\s[-–|]\s", title_text)
            if not parts:
                continue

            name = parts[0].strip()
            job_title = parts[1].strip() if len(parts) > 1 else "Recruiter"

            if len(name.split()) > 4:
                continue
            if any(k in name.lower() for k in ("jobs", "careers", "hiring", "linkedin", "profile")):
                continue
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            people.append((name, job_title))

        return people

    @staticmethod
    def _normalize_domain(domain: str, company: str) -> str:
        cleaned = clean_domain(domain)
        if cleaned and not is_job_board_host(cleaned):
            return cleaned
        if company:
            return slug_domain_guess(company)
        return ""
