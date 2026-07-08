"""Jobicy remote-jobs API scraper (free, no key required)."""

import logging
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.services.scraper.base import RawJob

logger = logging.getLogger(__name__)


def _parse_date(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return None


class JobicyScraper:
    source_name = "jobicy"
    api_url = "https://jobicy.com/api/v2/remote-jobs"

    async def fetch_jobs(self, limit: int = 100, roles: Optional[list[str]] = None) -> list[RawJob]:
        searches = [r for r in (roles or []) if r] or [""]

        jobs: list[RawJob] = []
        seen: set[str] = set()
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                for term in searches:
                    if len(jobs) >= limit:
                        break
                    params: dict[str, object] = {"count": min(limit, 50)}
                    if term:
                        params["tag"] = term
                    try:
                        response = await client.get(
                            self.api_url,
                            headers={"User-Agent": "relocation-job-hunter/1.0"},
                            params=params,
                        )
                        response.raise_for_status()
                        data = response.json()
                    except Exception as exc:
                        logger.warning("Jobicy search '%s' failed: %s", term, exc)
                        continue

                    for item in data.get("jobs", []):
                        if len(jobs) >= limit:
                            break
                        external_id = f"jobicy-{item.get('id', '')}"
                        if external_id in seen:
                            continue
                        seen.add(external_id)

                        raw_desc = item.get("jobDescription") or item.get("jobExcerpt") or ""
                        description = BeautifulSoup(raw_desc, "lxml").get_text(" ", strip=True)
                        tags = []
                        for key in ("jobIndustry", "jobType"):
                            val = item.get(key)
                            if isinstance(val, list):
                                tags.extend(str(v).lower() for v in val)
                            elif val:
                                tags.append(str(val).lower())

                        jobs.append(
                            RawJob(
                                external_id=external_id,
                                source=self.source_name,
                                title=item.get("jobTitle") or "Unknown",
                                company=item.get("companyName") or "Unknown",
                                url=item.get("url") or "https://jobicy.com",
                                description=description,
                                location=item.get("jobGeo") or "Remote",
                                posted_at=_parse_date(item.get("pubDate")),
                                tags=tags,
                            )
                        )
        except Exception as exc:
            logger.warning("Jobicy scraper failed: %s", exc)
        return jobs
