"""Best-effort import of a single job posting from an arbitrary URL.

Tries, in order: schema.org JobPosting JSON-LD, OpenGraph/meta tags, then the
page <title>. Returns whatever could be extracted plus a `scraped` flag and a
list of `missing` core fields so the UI can ask the user to fill the gaps.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.scraper.base import parse_salary

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Hosts that are job boards/aggregators rather than the employer itself, so we
# don't mistake them for the company's email domain.
_JOB_BOARD_HOSTS = {
    "linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com",
    "monster.com", "lever.co", "greenhouse.io", "myworkdayjobs.com",
    "workable.com", "ashbyhq.com", "smartrecruiters.com", "totaljobs.com",
    "reed.co.uk", "otta.com", "wellfound.com", "angel.co", "remoteok.com",
    "remoteok.io", "weworkremotely.com", "remotive.com", "relocate.me",
    "google.com", "bing.com", "jobs.lever.co", "boards.greenhouse.io",
}

_CORE_FIELDS = ("title", "company", "description")


def _registrable_domain(host: str) -> str:
    host = (host or "").lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


def _is_job_board(host: str) -> bool:
    host = (host or "").lower()
    return any(host == b or host.endswith("." + b) for b in _JOB_BOARD_HOSTS)


def _clean_text(html_or_text: str) -> str:
    if not html_or_text:
        return ""
    if "<" in html_or_text and ">" in html_or_text:
        soup = BeautifulSoup(html_or_text, "lxml")
        for br in soup.find_all("br"):
            br.replace_with("\n")
        text = soup.get_text("\n")
    else:
        text = html_or_text
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_date(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _iter_jsonld_objects(data: Any):
    """Yield every dict in a JSON-LD payload (handling lists and @graph)."""
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld_objects(item)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _iter_jsonld_objects(data["@graph"])


def _find_job_posting(soup: BeautifulSoup) -> Optional[dict]:
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        for obj in _iter_jsonld_objects(data):
            types = obj.get("@type")
            types = types if isinstance(types, list) else [types]
            if any(str(t).lower() == "jobposting" for t in types):
                return obj
    return None


def _org_domain(org: Any, page_host: str) -> str:
    """Resolve the employer's email domain from JSON-LD, else the page host."""
    if isinstance(org, dict):
        for key in ("sameAs", "url"):
            val = org.get(key)
            if isinstance(val, str) and val.startswith("http"):
                host = urlparse(val).netloc
                if host and not _is_job_board(host):
                    return _registrable_domain(host)
    if page_host and not _is_job_board(page_host):
        return _registrable_domain(page_host)
    return ""


def _extract_location(job_location: Any) -> str:
    locs = job_location if isinstance(job_location, list) else [job_location]
    parts: list[str] = []
    for loc in locs:
        if not isinstance(loc, dict):
            continue
        addr = loc.get("address")
        if isinstance(addr, dict):
            for key in ("addressLocality", "addressRegion", "addressCountry"):
                val = addr.get(key)
                if isinstance(val, dict):
                    val = val.get("name")
                if isinstance(val, str) and val.strip():
                    parts.append(val.strip())
        elif isinstance(addr, str):
            parts.append(addr.strip())
    # De-dupe while preserving order.
    seen: set[str] = set()
    out = [p for p in parts if not (p in seen or seen.add(p))]
    return ", ".join(out)


def _from_json_ld(job: dict, page_host: str) -> dict:
    salary_text = ""
    salary_min = salary_max = None
    salary_currency = ""
    base = job.get("baseSalary")
    if isinstance(base, dict):
        currency = base.get("currency") or ""
        value = base.get("value")
        if isinstance(value, dict):
            smin = value.get("minValue")
            smax = value.get("maxValue") or value.get("value")
            try:
                salary_min = int(float(smin)) if smin is not None else None
                salary_max = int(float(smax)) if smax is not None else None
            except (TypeError, ValueError):
                pass
            if salary_min or salary_max:
                lo, hi = salary_min or salary_max, salary_max or salary_min
                salary_text = f"{currency} {lo:,}" + (f" - {hi:,}" if hi != lo else "")
                salary_currency = currency

    return {
        "title": _clean_text(job.get("title") or ""),
        "company": _clean_text(
            (job.get("hiringOrganization") or {}).get("name", "")
            if isinstance(job.get("hiringOrganization"), dict)
            else ""
        ),
        "company_domain": _org_domain(job.get("hiringOrganization"), page_host),
        "location": _extract_location(job.get("jobLocation")),
        "description": _clean_text(job.get("description") or ""),
        "posted_at": _parse_date(job.get("datePosted")),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_currency": salary_currency,
        "salary_text": salary_text,
    }


def _meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        el = soup.find("meta", property=name) or soup.find("meta", attrs={"name": name})
        if el and el.get("content"):
            return el["content"].strip()
    return ""


async def import_job_from_url(url: str) -> dict:
    """Fetch and parse a job posting URL. Never raises for unscrapeable pages;
    instead returns the partial result with scraped=False and missing fields."""
    page_host = urlparse(url).netloc
    result: dict = {
        "url": url,
        "title": "",
        "company": "",
        "company_domain": "",
        "location": "",
        "description": "",
        "posted_at": None,
        "salary_min": None,
        "salary_max": None,
        "salary_currency": "",
        "salary_text": "",
        "scraped": False,
        "missing": list(_CORE_FIELDS),
        "message": "",
    }

    html = ""
    try:
        async with httpx.AsyncClient(
            timeout=20.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        logger.info("URL import fetch failed for %s: %s", url, exc)
        result["message"] = (
            "Couldn't fetch this link automatically. Please fill in the job details below."
        )
        return result

    soup = BeautifulSoup(html, "lxml")

    job = _find_job_posting(soup)
    if job:
        result.update({k: v for k, v in _from_json_ld(job, page_host).items()})

    # Fill any gaps from OpenGraph / meta / <title>.
    if not result["title"]:
        result["title"] = _meta(soup, "og:title", "twitter:title") or (
            soup.title.get_text(strip=True) if soup.title else ""
        )
    if not result["company"]:
        result["company"] = _meta(soup, "og:site_name")
    if not result["description"]:
        result["description"] = _clean_text(_meta(soup, "og:description", "description"))
    if not result["company_domain"] and page_host and not _is_job_board(page_host):
        result["company_domain"] = _registrable_domain(page_host)

    # Best-effort salary from the description text if JSON-LD didn't carry it.
    if not result["salary_text"]:
        smin, smax, currency, label = parse_salary(
            " ".join([result["title"], result["description"]])
        )
        result.update(
            salary_min=smin, salary_max=smax, salary_currency=currency, salary_text=label
        )

    result["missing"] = [f for f in _CORE_FIELDS if not result.get(f)]
    result["scraped"] = bool(result["title"]) and not ({"title", "company"} & set(result["missing"]))
    if result["scraped"] and result["missing"]:
        result["message"] = (
            "Imported partial details. Review and complete the highlighted fields."
        )
    elif not result["scraped"]:
        result["message"] = (
            "This site blocked automatic import or had no job data. "
            "Please fill in the job details below."
        )
    return result
