"""LinkedIn guest job-search scraper using direct search query params."""

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.services.scraper.base import RawJob
from app.services.scraper.linkedin_query import (
    GUEST_SEARCH_URL,
    build_linkedin_search_params,
)

logger = logging.getLogger(__name__)

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

    async def fetch_jobs(
        self,
        limit: int = 80,
        roles: Optional[list[str]] = None,
        locations: Optional[list[str]] = None,
        age_hours: int = 48,
        experience_codes: Optional[str] = None,
        salary_bucket: Optional[str] = None,
        work_type_codes: Optional[list[str]] = None,
        exclude_external_ids: Optional[set[str]] = None,
    ) -> list[RawJob]:
        role_terms = [r for r in (roles or []) if r][: self.MAX_ROLES] or [""]
        location_terms = [loc for loc in (locations or []) if loc][: self.MAX_LOCATIONS]
        if not location_terms:
            location_terms = [""]

        exclude = exclude_external_ids or set()
        global_limit = compute_fetch_limit(requested=limit, locations=location_terms)
        # Paginate deeper on repeat searches when many results are already saved.
        fetch_cap = min(
            GLOBAL_FETCH_CAP,
            global_limit + min(len(exclude), 250),
        )
        target_new = global_limit
        per_location_target = (
            max(JOBS_PER_LOCATION, target_new // len(location_terms))
            if len(location_terms) >= MIN_LOCATIONS_FOR_QUOTA
            else target_new
        )
        pages_per_query = self.PAGES_PER_QUERY + (4 if exclude else 0)

        def is_new(job_id: str) -> bool:
            return f"linkedin-{job_id}" not in exclude

        cards: dict[str, dict] = {}
        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        ) as client:
            # Location-first so every country is queried before the global cap fills up.
            for location in location_terms:
                location_new = sum(
                    1
                    for card in cards.values()
                    if card.get("search_location") == location and is_new(card["job_id"])
                )
                for role in role_terms:
                    new_count = sum(1 for card in cards.values() if is_new(card["job_id"]))
                    if new_count >= target_new:
                        break
                    if location_new >= per_location_target:
                        break
                    for page in range(pages_per_query):
                        new_count = sum(1 for card in cards.values() if is_new(card["job_id"]))
                        if new_count >= target_new:
                            break
                        if len(cards) >= fetch_cap:
                            break
                        if location_new >= per_location_target:
                            break
                        start = page * self.PAGE_SIZE
                        found = await self._search(
                            client,
                            keywords=role,
                            location=location,
                            age_hours=age_hours,
                            start=start,
                            experience_codes=experience_codes,
                            salary_bucket=salary_bucket,
                            work_type_codes=work_type_codes,
                        )
                        if not found:
                            break
                        for card in found:
                            if len(cards) >= fetch_cap:
                                break
                            if card["job_id"] and card["job_id"] not in cards:
                                card["search_location"] = location
                                cards[card["job_id"]] = card
                                if is_new(card["job_id"]):
                                    location_new += 1
                        await asyncio.sleep(0.5)
                await asyncio.sleep(1.0)

            new_cards = [card for card in cards.values() if is_new(card["job_id"])]
            selected = new_cards[:target_new]

            logger.info(
                "LinkedIn fetched %d new cards (%d total scraped, target=%d, locations=%d)",
                len(selected),
                len(cards),
                target_new,
                len(location_terms),
            )

            semaphore = asyncio.Semaphore(4)

            async def enrich(card: dict) -> None:
                async with semaphore:
                    await asyncio.sleep(0.35)
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
                    search_location=card.get("search_location") or "",
                )
            )
        return jobs

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
