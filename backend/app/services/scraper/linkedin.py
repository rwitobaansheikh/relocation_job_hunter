"""LinkedIn guest job-search scraper using direct search query params."""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Optional, Union

import httpx
from bs4 import BeautifulSoup

from app.services.scraper.base import RawJob
from app.services.scraper.linkedin_query import (
    GUEST_SEARCH_URL,
    build_linkedin_search_params,
)

logger = logging.getLogger(__name__)

IsCancelled = Callable[[], Awaitable[bool]]
StreamItem = Union[RawJob, dict]

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# When searching 5+ countries, aim for at least this many unique jobs total.
MIN_JOBS_MULTI_COUNTRY = 100
MIN_LOCATIONS_FOR_QUOTA = 5
JOBS_PER_LOCATION = 25
GLOBAL_FETCH_CAP = 400


def compute_fetch_limit(
    *,
    requested: int = 100,
    locations: Optional[list[str]] = None,
) -> int:
    """Scale LinkedIn fetch budget so multi-country searches reach 100+ jobs."""
    geo = [loc for loc in (locations or []) if loc]
    if len(geo) >= MIN_LOCATIONS_FOR_QUOTA:
        return min(GLOBAL_FETCH_CAP, max(requested, MIN_JOBS_MULTI_COUNTRY, len(geo) * JOBS_PER_LOCATION))
    return min(GLOBAL_FETCH_CAP, max(requested, 150))


class LinkedInScraper:
    source_name = "linkedin"
    search_url = GUEST_SEARCH_URL
    detail_url = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

    MAX_ROLES = 8
    MAX_LOCATIONS = 15
    PAGES_PER_QUERY = 8
    PAGE_SIZE = 25
    MAX_RETRIES = 3

    async def fetch_jobs_stream(
        self,
        roles: Optional[list[str]] = None,
        location: str = "",
        age_hours: int = 48,
        experience_codes: Optional[str] = None,
        salary_bucket: Optional[str] = None,
        work_type_codes: Optional[list[str]] = None,
        exclude_external_ids: Optional[set[str]] = None,
        is_cancelled: IsCancelled | None = None,
    ):
        role_terms = [r for r in (roles or []) if r][: self.MAX_ROLES] or [""]
        location_term = location.strip()
        exclude = exclude_external_ids or set()

        async def cancelled() -> bool:
            return is_cancelled is not None and await is_cancelled()

        def is_new(job_id: str) -> bool:
            return f"linkedin-{job_id}" not in exclude

        fetch_cap = 500
        cards: dict[str, dict] = {}

        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        ) as client:
            for role in role_terms:
                page = 0
                while True:
                    if await cancelled():
                        return
                    if len(cards) >= fetch_cap:
                        break

                    role_label = role or "all roles"
                    loc_label = location_term or "worldwide"
                    yield {
                        "type": "progress",
                        "message": f'Searching LinkedIn for "{role_label}" in {loc_label}, page {page + 1}…',
                        "role": role,
                        "location": location_term,
                        "page": page + 1,
                    }

                    start = page * self.PAGE_SIZE
                    found = await self._search(
                        client,
                        keywords=role,
                        location=location_term,
                        age_hours=age_hours,
                        start=start,
                        experience_codes=experience_codes,
                        salary_bucket=salary_bucket,
                        work_type_codes=work_type_codes,
                    )
                    if not found:
                        break

                    for card in found:
                        if await cancelled():
                            return
                        if len(cards) >= fetch_cap:
                            break
                        job_id = card.get("job_id")
                        if job_id and job_id not in cards:
                            card["search_location"] = location_term
                            cards[job_id] = card

                            if is_new(job_id):
                                yield {
                                    "type": "progress",
                                    "message": f'Loading details: {card["title"]} at {card["company"]}…',
                                    "role": role,
                                    "location": location_term,
                                }
                                await asyncio.sleep(0.35)
                                if await cancelled():
                                    return
                                card["description"] = await self._fetch_description(client, job_id)
                                yield RawJob(
                                    external_id=f"linkedin-{job_id}",
                                    source=self.source_name,
                                    title=card["title"],
                                    company=card["company"],
                                    url=card["url"],
                                    location=card["location"],
                                    posted_at=card["posted_at"],
                                    description=card.get("description", ""),
                                    search_location=location_term,
                                )

                    await asyncio.sleep(2.5)
                    page += 1

                    if page >= self.PAGES_PER_QUERY:
                        break
                await asyncio.sleep(1.0)


    async def _search(
        self,
        client: httpx.AsyncClient,
        keywords: str,
        location: str,
        age_hours: int,
        start: int = 0,
        experience_codes: Optional[str] = None,
        salary_bucket: Optional[str] = None,
        work_type_codes: Optional[list[str]] = None,
    ) -> list[dict]:
        params = build_linkedin_search_params(
            keywords=keywords,
            location=location,
            age_hours=age_hours,
            experience_codes=experience_codes,
            work_type_codes=work_type_codes,
            salary_bucket=salary_bucket,
            start=start,
        )
        for attempt in range(self.MAX_RETRIES):
            try:
                response = await client.get(self.search_url, params=params)
                if response.status_code == 429:
                    wait = 2 ** attempt + 1
                    logger.warning(
                        "LinkedIn rate limited (429), retry %d/%d in %ds",
                        attempt + 1,
                        self.MAX_RETRIES,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                response.raise_for_status()
                return self._parse_result_cards(response.text)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429 and attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt + 1)
                    continue
                logger.warning("LinkedIn search failed (params=%s): %s", params, exc)
                return []
            except Exception as exc:
                logger.warning("LinkedIn search failed (params=%s): %s", params, exc)
                return []
        return []

    def _parse_result_cards(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
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

            link_el = li.select_one("a.base-card__full-link") or li.select_one(
                "a[class*='base-card']"
            )
            url = (link_el.get("href") if link_el else "") or ""
            if not job_id:
                job_id = self._job_id_from_url(url)
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

    @staticmethod
    def _job_id_from_url(url: str) -> str:
        match = re.search(r"/jobs/view/(\d+)", url or "")
        return match.group(1) if match else ""

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
