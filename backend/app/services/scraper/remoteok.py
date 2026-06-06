"""RemoteOK public API scraper — relocation-friendly remote jobs."""

from datetime import datetime, timezone
from typing import Optional

import httpx

from app.services.scraper.base import RawJob


class RemoteOKScraper:
    source_name = "remoteok"
    api_url = "https://remoteok.com/api"

    async def fetch_jobs(self, limit: int = 200, roles: Optional[list[str]] = None) -> list[RawJob]:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                self.api_url,
                headers={"User-Agent": "relocation-job-hunter/1.0"},
            )
            response.raise_for_status()
            data = response.json()

        jobs: list[RawJob] = []
        for item in data[1 : limit + 1]:
            if not isinstance(item, dict):
                continue

            posted_at = None
            epoch = item.get("epoch")
            if epoch:
                posted_at = datetime.fromtimestamp(int(epoch), tz=timezone.utc).replace(tzinfo=None)

            tags = item.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]

            jobs.append(
                RawJob(
                    external_id=f"remoteok-{item.get('id', item.get('slug', ''))}",
                    source=self.source_name,
                    title=item.get("position") or item.get("title") or "Unknown",
                    company=item.get("company") or "Unknown",
                    url=item.get("url") or item.get("apply_url") or "https://remoteok.com",
                    description=item.get("description") or "",
                    location=item.get("location") or "Remote",
                    company_domain=(item.get("company") or "").lower().replace(" ", "") + ".com",
                    posted_at=posted_at,
                    tags=[str(t).lower() for t in tags],
                )
            )
        return jobs
