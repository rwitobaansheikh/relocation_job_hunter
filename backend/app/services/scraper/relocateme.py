"""Relocate.me scraper — jobs explicitly offering relocation support."""

import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.services.scraper.base import RawJob


class RelocateMeScraper:
    source_name = "relocateme"
    base_url = "https://relocate.me"

    async def fetch_jobs(self, limit: int = 50, roles: Optional[list[str]] = None) -> list[RawJob]:
        jobs: list[RawJob] = []
        params: dict[str, object] = {"experience": "junior,graduate,intern"}
        if roles:
            params["query"] = " ".join(roles[:3])
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                f"{self.base_url}/search",
                headers={"User-Agent": "relocation-job-hunter/1.0"},
                params=params,
            )
            if response.status_code != 200:
                return jobs

            soup = BeautifulSoup(response.text, "lxml")
            cards = soup.select(".job-card, .vacancy-card, article.job, .search-result-item")

            for card in cards[:limit]:
                title_el = card.select_one("h2 a, h3 a, .job-title a, a.title")
                if not title_el:
                    continue

                title = title_el.get_text(strip=True)
                url = title_el.get("href", "")
                if url and not url.startswith("http"):
                    url = f"{self.base_url}{url}"

                company_el = card.select_one(".company, .company-name, .employer")
                company = company_el.get_text(strip=True) if company_el else "Unknown"

                location_el = card.select_one(".location, .country, .job-location")
                location = location_el.get_text(strip=True) if location_el else ""

                desc_el = card.select_one(".description, .snippet, p")
                description = desc_el.get_text(strip=True) if desc_el else ""

                external_id = f"relocateme-{re.sub(r'[^a-z0-9]', '', url.lower())[:50]}"

                jobs.append(
                    RawJob(
                        external_id=external_id,
                        source=self.source_name,
                        title=title,
                        company=company,
                        url=url,
                        description=description,
                        location=location,
                        # The search cards carry no reliable posting date; a
                        # faked utcnow() exempted these jobs from age filters.
                        posted_at=None,
                        tags=["relocation"],
                    )
                )
        return jobs
