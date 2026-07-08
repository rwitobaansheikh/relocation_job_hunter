"""Google Jobs scraper via the SerpAPI google_jobs engine. Requires SERPAPI_API_KEY."""

import logging
import re
from datetime import datetime, timedelta
from typing import Optional

import httpx

from app.config import settings
from app.services.scraper.base import RawJob

logger = logging.getLogger(__name__)

_RELATIVE_RE = re.compile(r"(\d+)\s+(minute|hour|day|week|month)s?\s+ago", re.IGNORECASE)
_UNIT_TO_DELTA = {
    "minute": timedelta(minutes=1),
    "hour": timedelta(hours=1),
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=30),
}


def parse_relative_date(value: str | None) -> Optional[datetime]:
    """Parse Google's relative dates like '3 days ago' into a datetime."""
    if not value:
        return None
    m = _RELATIVE_RE.search(value)
    if not m:
        return None
    count, unit = int(m.group(1)), m.group(2).lower()
    return datetime.utcnow() - _UNIT_TO_DELTA[unit] * count


class GoogleJobsScraper:
    source_name = "googlejobs"
    api_url = "https://serpapi.com/search.json"

    async def fetch_jobs(self, limit: int = 100, roles: Optional[list[str]] = None) -> list[RawJob]:
        if not settings.serpapi_api_key:
            return []
        searches = [r for r in (roles or []) if r]
        if not searches:
            return []

        jobs: list[RawJob] = []
        seen: set[str] = set()
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                for term in searches:
                    if len(jobs) >= limit:
                        break
                    try:
                        response = await client.get(
                            self.api_url,
                            params={
                                "engine": "google_jobs",
                                "q": term,
                                "api_key": settings.serpapi_api_key,
                            },
                        )
                        response.raise_for_status()
                        data = response.json()
                    except Exception as exc:
                        logger.warning("Google Jobs search '%s' failed: %s", term, exc)
                        continue

                    for item in data.get("jobs_results", []):
                        if len(jobs) >= limit:
                            break
                        job_id = item.get("job_id") or ""
                        external_id = f"googlejobs-{job_id[:60]}"
                        if not job_id or external_id in seen:
                            continue
                        seen.add(external_id)

                        apply_options = item.get("apply_options") or []
                        url = ""
                        if apply_options:
                            url = apply_options[0].get("link") or ""
                        url = url or item.get("share_link") or "https://www.google.com/search?q=" + term

                        extensions = item.get("detected_extensions") or {}
                        jobs.append(
                            RawJob(
                                external_id=external_id,
                                source=self.source_name,
                                title=item.get("title") or "Unknown",
                                company=item.get("company_name") or "Unknown",
                                url=url,
                                description=item.get("description") or "",
                                location=item.get("location") or "",
                                posted_at=parse_relative_date(extensions.get("posted_at")),
                                tags=[],
                            )
                        )
        except Exception as exc:
            logger.warning("Google Jobs scraper failed: %s", exc)
        return jobs
