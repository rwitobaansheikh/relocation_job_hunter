"""Reed.co.uk jobseeker API scraper (UK-focused). Requires REED_API_KEY."""

import logging
from datetime import datetime
from typing import Optional

import httpx

from app.config import settings
from app.services.scraper.base import RawJob

logger = logging.getLogger(__name__)


def _parse_reed_date(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y")
    except ValueError:
        return None


class ReedScraper:
    source_name = "reed"
    api_url = "https://www.reed.co.uk/api/1.0/search"

    async def fetch_jobs(self, limit: int = 100, roles: Optional[list[str]] = None) -> list[RawJob]:
        if not settings.reed_api_key:
            return []
        searches = [r for r in (roles or []) if r] or [""]

        jobs: list[RawJob] = []
        seen: set[str] = set()
        try:
            auth = httpx.BasicAuth(settings.reed_api_key, "")
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, auth=auth) as client:
                for term in searches:
                    if len(jobs) >= limit:
                        break
                    params: dict[str, object] = {"resultsToTake": min(limit, 100)}
                    if term:
                        params["keywords"] = term
                    try:
                        response = await client.get(
                            self.api_url,
                            headers={"User-Agent": "relocation-job-hunter/1.0"},
                            params=params,
                        )
                        response.raise_for_status()
                        data = response.json()
                    except Exception as exc:
                        logger.warning("Reed search '%s' failed: %s", term, exc)
                        continue

                    for item in data.get("results", []):
                        if len(jobs) >= limit:
                            break
                        external_id = f"reed-{item.get('jobId', '')}"
                        if external_id in seen:
                            continue
                        seen.add(external_id)

                        # Reed mixes daily/hourly rates into the same fields;
                        # only keep plausible annual figures.
                        smin = item.get("minimumSalary")
                        smax = item.get("maximumSalary")
                        if smin and smin < 1000:
                            smin = None
                        if smax and smax < 1000:
                            smax = None
                        jobs.append(
                            RawJob(
                                external_id=external_id,
                                source=self.source_name,
                                title=item.get("jobTitle") or "Unknown",
                                company=item.get("employerName") or "Unknown",
                                url=item.get("jobUrl") or "https://www.reed.co.uk",
                                description=item.get("jobDescription") or "",
                                location=item.get("locationName") or "",
                                posted_at=_parse_reed_date(item.get("date")),
                                salary_min=int(smin) if smin else None,
                                salary_max=int(smax) if smax else None,
                                salary_currency="£",
                                tags=[],
                            )
                        )
        except Exception as exc:
            logger.warning("Reed scraper failed: %s", exc)
        return jobs
