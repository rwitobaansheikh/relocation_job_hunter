"""LinkedIn public/guest job-search scraper.

Ported from an n8n workflow. The flow is:
  1. Build a LinkedIn guest job-search query from the profile's target roles
     (keywords), target countries (location), the early-career experience codes,
     and the 48h freshness window (f_TPR=r{seconds}).
  2. Parse the returned job cards into (job_id, title, company, location, date).
  3. Fetch each posting's guest detail page for the full description.

Notes / caveats:
  - This hits LinkedIn's unauthenticated `jobs-guest` endpoints (the same ones
    the public "see more jobs" pager uses). No login/cookies are required, but
    LinkedIn rate-limits aggressively, so requests are bounded and throttled.
  - Scraping LinkedIn may conflict with their Terms of Service; use responsibly.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.services.scraper.base import RawJob

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class LinkedInScraper:
    source_name = "linkedin"
    search_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    detail_url = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

    # f_E experience codes: 1 = Internship, 2 = Entry level, 3 = Associate.
    # These map onto the app's allowed intern / junior / graduate levels.
    EXPERIENCE_CODES = "1,2,3"

    # Bound the request fan-out so we don't hammer LinkedIn. LinkedIn is the
    # primary source, so these are generous; each page returns ~25 cards.
    MAX_ROLES = 5
    MAX_LOCATIONS = 5
    PAGES_PER_QUERY = 4
    PAGE_SIZE = 25

    async def fetch_jobs(
        self,
        limit: int = 80,
        roles: Optional[list[str]] = None,
        locations: Optional[list[str]] = None,
        age_hours: int = 48,
        experience_codes: Optional[str] = None,
        salary_bucket: Optional[str] = None,
    ) -> list[RawJob]:
        role_terms = [r for r in (roles or []) if r][: self.MAX_ROLES] or [""]
        location_terms = [loc for loc in (locations or []) if loc][: self.MAX_LOCATIONS] or [""]
        seconds = max(int(age_hours), 1) * 3600
        fe_codes = experience_codes or self.EXPERIENCE_CODES

        cards: dict[str, dict] = {}
        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        ) as client:
            for role in role_terms:
                if len(cards) >= limit:
                    break
                for location in location_terms:
                    if len(cards) >= limit:
                        break
                    for page in range(self.PAGES_PER_QUERY):
                        if len(cards) >= limit:
                            break
                        start = page * self.PAGE_SIZE
                        found = await self._search(
                            client, role, location, seconds, start, fe_codes, salary_bucket
                        )
                        if not found:
                            break  # no more results for this query
                        for card in found:
                            if card["job_id"] and card["job_id"] not in cards:
                                cards[card["job_id"]] = card

            selected = list(cards.values())[:limit]

            # Fetch descriptions with limited concurrency + a small delay so we
            # stay polite and reduce the chance of being rate-limited.
            semaphore = asyncio.Semaphore(4)

            async def enrich(card: dict) -> None:
                async with semaphore:
                    await asyncio.sleep(0.4)
                    card["description"] = await self._fetch_description(client, card["job_id"])

            await asyncio.gather(*(enrich(c) for c in selected), return_exceptions=True)

        jobs: list[RawJob] = []
        for card in selected:
            jobs.append(
                RawJob(
                    external_id=f"linkedin-{card['job_id']}",
                    source=self.source_name,
                    title=card.get("title") or "Unknown",
                    company=card.get("company") or "Unknown",
                    url=card.get("url") or f"https://www.linkedin.com/jobs/view/{card['job_id']}",
                    description=card.get("description") or "",
                    location=card.get("location") or "",
                    company_domain="",
                    posted_at=card.get("posted_at"),
                    tags=[],
                )
            )
        return jobs

    async def _search(
        self,
        client: httpx.AsyncClient,
        keywords: str,
        location: str,
        seconds: int,
        start: int = 0,
        fe_codes: Optional[str] = None,
        salary_bucket: Optional[str] = None,
    ) -> list[dict]:
        params: dict[str, object] = {
            "f_TPR": f"r{seconds}",
            "f_E": fe_codes or self.EXPERIENCE_CODES,
            "start": start,
        }
        if salary_bucket:
            params["f_SB2"] = salary_bucket
        if keywords:
            params["keywords"] = keywords
        if location:
            params["location"] = location

        try:
            response = await client.get(self.search_url, params=params)
            response.raise_for_status()
        except Exception as exc:
            logger.warning("LinkedIn search failed (kw=%r loc=%r): %s", keywords, location, exc)
            return []

        soup = BeautifulSoup(response.text, "lxml")
        results: list[dict] = []
        for li in soup.select("li"):
            card = li.select_one("div.base-card") or li.select_one("div[class*='base-card']")
            if not card:
                continue

            job_id = ""
            urn = card.get("data-entity-urn", "")
            match = re.search(r"jobPosting:(\d+)", urn)
            if match:
                job_id = match.group(1)

            link_el = li.select_one("a.base-card__full-link") or li.select_one("a[class*='base-card']")
            url = (link_el.get("href") if link_el else "") or ""
            if not job_id and url:
                url_match = re.search(r"/jobs/view/(\d+)", url)
                if url_match:
                    job_id = url_match.group(1)
            if not job_id:
                continue

            title_el = li.select_one("h3.base-search-card__title")
            company_el = li.select_one("h4.base-search-card__subtitle a") or li.select_one(
                "h4.base-search-card__subtitle"
            )
            location_el = li.select_one("span.job-search-card__location")

            posted_at = None
            time_el = li.select_one("time")
            if time_el and time_el.get("datetime"):
                try:
                    posted_at = datetime.fromisoformat(time_el["datetime"]).replace(tzinfo=None)
                except ValueError:
                    pass

            results.append(
                {
                    "job_id": job_id,
                    "url": url.split("?")[0],
                    "title": title_el.get_text(strip=True) if title_el else "",
                    "company": company_el.get_text(strip=True) if company_el else "",
                    "location": location_el.get_text(strip=True) if location_el else "",
                    "posted_at": posted_at,
                }
            )
        return results

    async def _fetch_description(self, client: httpx.AsyncClient, job_id: str) -> str:
        try:
            response = await client.get(self.detail_url.format(job_id=job_id))
            response.raise_for_status()
        except Exception as exc:
            logger.debug("LinkedIn detail fetch failed for %s: %s", job_id, exc)
            return ""

        soup = BeautifulSoup(response.text, "lxml")
        desc_el = (
            soup.select_one("div.show-more-less-html__markup")
            or soup.select_one("div.description__text")
        )
        if not desc_el:
            return ""
        return re.sub(r"\s+", " ", desc_el.get_text(" ", strip=True)).strip()
