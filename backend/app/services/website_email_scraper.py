"""Discover company emails by scraping the corporate website and public search snippets."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(
    r"\b([a-zA-Z0-9][a-zA-Z0-9._%+'-]*@[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,})\b"
)

GENERIC_LOCALS = frozenset(
    {
        "careers",
        "jobs",
        "job",
        "talent",
        "recruiting",
        "recruitment",
        "hr",
        "hiring",
        "people",
        "hello",
        "info",
        "contact",
        "support",
        "apply",
        "recruiter",
        "recruiters",
        "hrteam",
        "humanresources",
    }
)

ROLE_KEYWORDS = (
    "recruit",
    "talent",
    "hr",
    "hiring",
    "people",
    "human resources",
    "career",
)

CAREER_PATHS = (
    "",
    "/careers",
    "/jobs",
    "/join-us",
    "/work-with-us",
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
    "/team",
    "/people",
    "/company",
)

GENERIC_LABELS = {
    "careers": ("HR Team", "Human Resources"),
    "jobs": ("Recruiting", "Recruiting"),
    "job": ("Recruiting", "Recruiting"),
    "talent": ("Talent", "Talent Acquisition"),
    "recruiting": ("Recruiting", "Recruiting"),
    "recruitment": ("Recruitment", "Recruitment"),
    "hr": ("HR Team", "Human Resources"),
    "hiring": ("Hiring Team", "Hiring"),
    "people": ("People Team", "People Operations"),
    "hello": ("Team", "General"),
    "contact": ("Contact", "General"),
    "info": ("Info", "General"),
    "apply": ("Applications", "Recruiting"),
}


@dataclass
class ScrapedEmail:
    email: str
    name: str
    title: str
    source: str  # website | search
    confidence: int
    verification_status: str = "found_on_site"


def _clean_domain(domain: str) -> str:
    text = (domain or "").strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"/.*$", "", text)
    return re.sub(r"^www\.", "", text)


def _is_role_email(local: str) -> bool:
    low = local.lower()
    return low in GENERIC_LOCALS or any(k in low for k in ("recruit", "talent", "hr", "hiring", "career"))


def _name_from_local(local: str) -> tuple[str, str]:
    """Best-effort person name + title from first.last style local parts."""
    if "." in local:
        parts = [p for p in local.split(".") if p and p.isalpha()]
        if len(parts) >= 2:
            name = " ".join(p.capitalize() for p in parts[:2])
            return name, "Recruiter"
    if local.isalpha() and len(local) > 2:
        return local.capitalize(), "Recruiter"
    label = GENERIC_LABELS.get(local.lower(), ("Hiring Team", "Recruiting"))
    return label[0], label[1]


def _extract_emails(text: str, domain: str) -> set[str]:
    domain = _clean_domain(domain)
    found: set[str] = set()
    for match in EMAIL_RE.findall(text or ""):
        email = match.strip().lower()
        if email.endswith(f"@{domain}") and not email.startswith("noreply@"):
            found.add(email)
    return found


def _page_confidence(path: str, local: str) -> int:
    path = (path or "").lower()
    if any(p in path for p in ("/career", "/job", "/contact", "/team", "/people", "/about")):
        return 82 if _is_role_email(local) else 88
    if _is_role_email(local):
        return 72
    return 78


class WebsiteEmailScraper:
    def __init__(self) -> None:
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; JobApplicationFlow/1.0; +https://jobapplicationflow.com)"
            ),
            "Accept": "text/html,application/xhtml+xml",
        }

    async def find_emails(self, company: str, domain: str, limit: int = 8) -> list[ScrapedEmail]:
        domain = _clean_domain(domain)
        if not domain:
            return []

        results: list[ScrapedEmail] = []
        seen: set[str] = set()

        async with httpx.AsyncClient(
            timeout=8.0,
            follow_redirects=True,
            headers=self._headers,
        ) as client:
            # Priority paths first — stop early once we have useful hits.
            priority_paths = ("", "/careers", "/jobs", "/contact", "/about")
            other_paths = tuple(p for p in CAREER_PATHS if p not in priority_paths)
            career_hosts = (
                domain,
                f"www.{domain}",
                f"careers.{domain}",
                f"jobs.{domain}",
            )

            for host in career_hosts:
                if len(results) >= limit:
                    break
                for path_group in (priority_paths, other_paths):
                    for path in path_group:
                        if len(results) >= limit:
                            break
                        added = await self._scrape_path(client, host, path, seen)
                        results.extend(added)
                        if len(results) >= 2 and path in ("/careers", "/jobs", "/contact"):
                            break
                    if len(results) >= limit:
                        break
                if len(results) >= 2:
                    break

            if len(results) < limit:
                for item in await self._search_snippets(client, company, domain):
                    if item.email in seen:
                        continue
                    seen.add(item.email)
                    results.append(item)
                    if len(results) >= limit:
                        break

        results.sort(key=lambda r: r.confidence, reverse=True)
        return results[:limit]

    async def _scrape_path(
        self,
        client: httpx.AsyncClient,
        host: str,
        path: str,
        seen: set[str],
    ) -> list[ScrapedEmail]:
        domain = _clean_domain(host.split("/")[0])
        found: list[ScrapedEmail] = []
        url = f"https://{host}{path}"
        try:
            res = await client.get(url)
            if res.status_code >= 400:
                return found
            emails = _extract_emails(res.text, domain)
            soup = BeautifulSoup(res.text, "html.parser")
            for tag in soup.select("a[href^=mailto:]"):
                href = tag.get("href", "")
                mail = href.split("mailto:", 1)[-1].split("?", 1)[0].strip().lower()
                if mail.endswith(f"@{domain}"):
                    emails.add(mail)

            for email in emails:
                if email in seen:
                    continue
                seen.add(email)
                local = email.split("@")[0]
                name, title = _name_from_local(local)
                found.append(
                    ScrapedEmail(
                        email=email,
                        name=name,
                        title=title,
                        source=f"website:{path or '/'}",
                        confidence=_page_confidence(path, local),
                    )
                )
        except Exception as exc:
            logger.debug("Website scrape failed for %s: %s", url, exc)
        return found

    async def _search_snippets(
        self, client: httpx.AsyncClient, company: str, domain: str
    ) -> list[ScrapedEmail]:
        """Pull @domain addresses from public search result snippets."""
        queries = [
            f'site:{domain} "@{domain}"',
            f'"{company}" recruiter "@{domain}"',
            f'site:{domain} (careers OR jobs OR recruiting OR talent) email',
            f'"{company}" careers email "@{domain}"',
        ]
        found: list[ScrapedEmail] = []
        seen: set[str] = set()

        for query in queries:
            try:
                res = await client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query, "kl": "us-en"},
                    headers={
                        **self._headers,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                if res.status_code != 200:
                    continue

                emails = _extract_emails(res.text, domain)
                soup = BeautifulSoup(res.text, "html.parser")
                for block in soup.select(".result__snippet, .result__body, .links_main"):
                    text = block.get_text(" ", strip=True)
                    emails.update(_extract_emails(text, domain))

                for link in soup.select("a.result__a, a.result__url"):
                    href = link.get("href", "")
                    if domain in href:
                        emails.update(_extract_emails(href, domain))

                for email in emails:
                    if email in seen:
                        continue
                    seen.add(email)
                    local = email.split("@")[0]
                    name, title = _name_from_local(local)
                    found.append(
                        ScrapedEmail(
                            email=email,
                            name=name,
                            title=title,
                            source="search",
                            confidence=68 if _is_role_email(local) else 74,
                        )
                    )
            except Exception as exc:
                logger.debug("Search snippet scrape failed for '%s': %s", query, exc)

        return found
