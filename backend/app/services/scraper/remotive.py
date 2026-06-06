"""Remotive public API scraper."""

from datetime import datetime
from typing import Optional

import httpx

from app.services.scraper.base import RawJob


class RemotiveScraper:
    source_name = "remotive"
    api_url = "https://remotive.com/api/remote-jobs"

    async def fetch_jobs(self, limit: int = 100, roles: Optional[list[str]] = None) -> list[RawJob]:
        # Remotive supports a server-side `search` term. When the profile has
        # target roles, query each one so we pull role-relevant listings rather
        # than the whole board; otherwise fall back to a single broad fetch.
        searches: list[Optional[str]] = [r for r in (roles or []) if r] or [None]

        jobs: list[RawJob] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for term in searches:
                if len(jobs) >= limit:
                    break
                params: dict[str, object] = {"limit": limit}
                if term:
                    params["search"] = term
                response = await client.get(
                    self.api_url,
                    headers={"User-Agent": "relocation-job-hunter/1.0"},
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

                for item in data.get("jobs", []):
                    if len(jobs) >= limit:
                        break
                    external_id = f"remotive-{item.get('id', '')}"
                    if external_id in seen:
                        continue
                    seen.add(external_id)

                    posted_at = None
                    pub_date = item.get("publication_date")
                    if pub_date:
                        try:
                            posted_at = datetime.fromisoformat(pub_date.replace("Z", "+00:00")).replace(tzinfo=None)
                        except ValueError:
                            pass

                    tags = [t.lower() for t in (item.get("tags") or [])]
                    company = item.get("company_name") or "Unknown"

                    jobs.append(
                        RawJob(
                            external_id=external_id,
                            source=self.source_name,
                            title=item.get("job_title") or "Unknown",
                            company=company,
                            url=item.get("url") or "https://remotive.com",
                            description=item.get("description") or "",
                            location=item.get("candidate_required_location") or "Remote",
                            company_domain=item.get("company_name", "").lower().replace(" ", "") + ".com",
                            posted_at=posted_at,
                            tags=tags,
                        )
                    )
        return jobs
