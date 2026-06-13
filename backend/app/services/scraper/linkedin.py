"""LinkedIn public/guest job-search scraper."""

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.services.scraper.base import RawJob
from app.services.scraper.linkedin_query import (
    GUEST_SEARCH_URL,
    PUBLIC_SEARCH_URL,
    build_linkedin_search_params,
    build_linkedin_search_url,
)

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class LinkedInScraper:
    source_name = "linkedin"
    search_url = GUEST_SEARCH_URL
    public_search_url = PUBLIC_SEARCH_URL
    detail_url = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

    MAX_ROLES = 8
    MAX_LOCATIONS = 15
    PAGES_PER_QUERY = 4
    PAGE_SIZE = 25
    MIN_PER_QUERY = 20

    async def fetch_jobs(
        self,
        limit: int = 80,
        roles: Optional[list[str]] = None,
        locations: Optional[list[str]] = None,
        age_hours: int = 48,
        experience_codes: Optional[str] = None,
        salary_bucket: Optional[str] = None,
        work_type_codes: Optional[list[str]] = None,
    ) -> list[RawJob]:
        role_terms = [r for r in (roles or []) if r][: self.MAX_ROLES] or [""]
        location_terms = [loc for loc in (locations or []) if loc][: self.MAX_LOCATIONS]
        if not location_terms:
            location_terms = [""]

        query_pairs = [(role, loc) for role in role_terms for loc in location_terms]
        per_query_cap = max(
            self.MIN_PER_QUERY,
            limit // max(len(query_pairs), 1) + 5,
        )

        cards: dict[str, dict] = {}
        async with httpx.AsyncClient(
            timeout=30.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
        ) as client:
            for role, location in query_pairs:
                if len(cards) >= limit:
                    break
                query_count = 0
                for page in range(self.PAGES_PER_QUERY):
                    if len(cards) >= limit or query_count >= per_query_cap:
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
                        if card["job_id"] and card["job_id"] not in cards:
                            card["search_location"] = location
                            cards[card["job_id"]] = card
                            query_count += 1
                            if query_count >= per_query_cap:
                                break

            selected = list(cards.values())[:limit]

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

        results = await self._search_guest_api(client, params)
        if not results:
            results = await self._search_public_page(client, params)
        return results

    async def _search_guest_api(
        self, client: httpx.AsyncClient, params: dict[str, str]
    ) -> list[dict]:
        try:
            response = await client.get(self.search_url, params=params)
            response.raise_for_status()
        except Exception as exc:
            logger.warning(
                "LinkedIn guest search failed (params=%s): %s", params, exc
            )
            return []

        return self._parse_result_cards(response.text)

    async def _search_public_page(
        self, client: httpx.AsyncClient, params: dict[str, str]
    ) -> list[dict]:
        """Fallback: fetch the public search page (n8n HTML extraction path)."""
        url = build_linkedin_search_url(params)
        try:
            response = await client.get(url)
            response.raise_for_status()
        except Exception as exc:
            logger.warning("LinkedIn public search failed (%s): %s", url, exc)
            return []

        soup = BeautifulSoup(response.text, "lxml")
        results: list[dict] = []
        for link_el in soup.select(
            'ul.jobs-search__results-list li div a[class*="base-card"]'
        ):
            href = (link_el.get("href") or "").strip()
            if not href:
                continue
            full_url = urljoin(self.public_search_url, href)
            job_id = self._job_id_from_url(full_url)
            if not job_id:
                continue
            results.append(
                {
                    "job_id": job_id,
                    "url": full_url.split("?")[0],
                    "title": link_el.get_text(strip=True) or "",
                    "company": "",
                    "location": "",
                    "posted_at": None,
                }
            )
        return results

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
