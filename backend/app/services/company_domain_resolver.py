"""Resolve the employer's email domain — never a job board or ATS host."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import dns.resolver
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Hosts that are boards/ATS — NOT the hiring company.
JOB_BOARD_HOSTS = frozenset(
    {
        "linkedin.com",
        "indeed.com",
        "glassdoor.com",
        "ziprecruiter.com",
        "monster.com",
        "lever.co",
        "greenhouse.io",
        "myworkdayjobs.com",
        "workable.com",
        "ashbyhq.com",
        "smartrecruiters.com",
        "totaljobs.com",
        "reed.co.uk",
        "otta.com",
        "wellfound.com",
        "angel.co",
        "remoteok.com",
        "remoteok.io",
        "weworkremotely.com",
        "remotive.com",
        "relocate.me",
        "google.com",
        "bing.com",
        "jobs.lever.co",
        "boards.greenhouse.io",
        "hackajob.com",
        "hackajob.co",
        "hackajob.co.uk",
        "jobstreet.com",
        "seek.com",
        "seek.com.au",
        "naukri.com",
        "dice.com",
        "careerbuilder.com",
        "simplyhired.com",
        "talent.com",
        "jobvite.com",
        "icims.com",
        "taleo.net",
        "bamboohr.com",
        "recruitee.com",
        "teamtailor.com",
        "breezy.hr",
        "apply.workable.com",
        "jobs.workable.com",
    }
)

_COMPANY_SUFFIXES = (
    "incorporated",
    "corporation",
    "company",
    "limited",
    "inc",
    "ltd",
    "llc",
    "gmbh",
    "ag",
    "sa",
    "bv",
    "plc",
    "co",
)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; JobApplicationFlow/1.0; +https://jobapplicationflow.com)"
)


def registrable_domain(host: str) -> str:
    host = (host or "").lower().split(":")[0].removeprefix("www.")
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def is_job_board_host(host: str) -> bool:
    host = (host or "").lower().removeprefix("www.")
    return any(host == b or host.endswith("." + b) for b in JOB_BOARD_HOSTS)


def clean_domain(value: str) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"/.*$", "", text)
    return text.removeprefix("www.")


def slug_domain_guess(company: str) -> str:
    """Best-effort {company}.com when no other signal exists."""
    slug = _company_slug(company)
    return f"{slug}.com" if slug else ""


def domain_has_mx(domain: str) -> bool:
    try:
        dns.resolver.resolve(domain, "MX")
        return True
    except Exception:
        return False


def _domain_from_url(url: str) -> str:
    if not url:
        return ""
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if not host or is_job_board_host(host):
        return ""
    return registrable_domain(host)


def _company_slug(company: str) -> str:
    text = (company or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = [w for w in text.split() if w]
    for suffix in _COMPANY_SUFFIXES:
        if words and words[-1] == suffix:
            words = words[:-1]
    return "".join(words)


def _domain_matches_company(domain: str, company: str) -> bool:
    slug = _company_slug(company)
    if not slug:
        return True
    host = domain.split(".")[0]
    return slug in host or host.startswith(slug) or host.endswith(slug)


async def _search_company_website(company: str) -> str:
    """Find the employer homepage via public search."""
    queries = [
        f'"{company}" official website',
        f'"{company}" careers jobs',
        f"{company} company website",
    ]
    headers = {"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9"}
    candidates: list[tuple[int, str]] = []

    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        for query in queries:
            for method, kwargs in (
                ("get", {"url": "https://html.duckduckgo.com/html/", "params": {"q": query}}),
                (
                    "post",
                    {
                        "url": "https://html.duckduckgo.com/html/",
                        "data": {"q": query, "kl": "us-en"},
                        "headers": {**headers, "Content-Type": "application/x-www-form-urlencoded"},
                    },
                ),
            ):
                try:
                    res = await client.request(method, headers=headers, **kwargs)
                    if res.status_code != 200:
                        continue
                    soup = BeautifulSoup(res.text, "html.parser")
                    for link in soup.select("a.result__a, a.result-link, h2 a"):
                        href = link.get("href", "")
                        if not href.startswith("http"):
                            continue
                        host = urlparse(href).netloc.lower().removeprefix("www.")
                        if not host or is_job_board_host(host):
                            continue
                        if any(
                            s in host
                            for s in ("linkedin.com", "facebook.com", "twitter.com", "instagram.com", "youtube.com")
                        ):
                            continue
                        domain = registrable_domain(host)
                        score = 0
                        if _domain_matches_company(domain, company):
                            score += 10
                        if "career" in host or "jobs" in host:
                            score += 3
                        if domain_has_mx(domain):
                            score += 2
                        candidates.append((score, domain))
                except Exception as exc:
                    logger.debug("Company domain search failed (%s): %s", query, exc)

    if not candidates:
        return ""

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_domain = candidates[0]
    if best_score >= 10:
        return best_domain
    # Prefer any search hit over a blind {company}.com guess.
    return best_domain


async def resolve_employer_domain(
    company: str,
    company_domain: str = "",
    job_url: str = "",
) -> str:
    """
    Return the hiring company's domain for email lookup.
    Never returns a job-board domain like hackajob.com or linkedin.com.
    """
    company = (company or "").strip()

    explicit = clean_domain(company_domain)
    if explicit and not is_job_board_host(explicit):
        return explicit

    from_url = _domain_from_url(job_url)
    if from_url:
        return from_url

    if company:
        searched = await _search_company_website(company)
        if searched:
            logger.info("Resolved %s -> %s via search", company, searched)
            return searched

        guess = slug_domain_guess(company)
        if guess and domain_has_mx(guess) and _domain_matches_company(guess, company):
            logger.info("Resolved %s -> %s via name heuristic (MX ok)", company, guess)
            return guess
        if guess:
            logger.info("Using unverified domain guess for %s: %s", company, guess)
            return guess

    return ""
