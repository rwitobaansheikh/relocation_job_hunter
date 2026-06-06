"""Remotive public API scraper."""

from datetime import datetime

import httpx

from app.services.scraper.base import RawJob


class RemotiveScraper:
    source_name = "remotive"
    api_url = "https://remotive.com/api/remote-jobs"

    async def fetch_jobs(self, limit: int = 100) -> list[RawJob]:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                self.api_url,
                headers={"User-Agent": "relocation-job-hunter/1.0"},
            )
            response.raise_for_status()
            data = response.json()

        jobs: list[RawJob] = []
        for item in data.get("jobs", [])[:limit]:
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
                    external_id=f"remotive-{item.get('id', '')}",
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
