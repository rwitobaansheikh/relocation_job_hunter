"""We Work Remotely RSS feed scraper."""

from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from app.services.scraper.base import RawJob


class WeWorkRemotelyScraper:
    source_name = "weworkremotely"
    feed_urls = [
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
        "https://weworkremotely.com/categories/remote-customer-support-jobs.rss",
    ]

    async def fetch_jobs(self, limit: int = 100) -> list[RawJob]:
        jobs: list[RawJob] = []
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for feed_url in self.feed_urls:
                if len(jobs) >= limit:
                    break
                response = await client.get(
                    feed_url,
                    headers={"User-Agent": "relocation-job-hunter/1.0"},
                )
                response.raise_for_status()
                feed = feedparser.parse(response.text)

                for entry in feed.entries:
                    if len(jobs) >= limit:
                        break

                    title = entry.get("title", "Unknown")
                    company = "Unknown"
                    if ":" in title:
                        parts = title.split(":", 1)
                        company = parts[0].strip()
                        title = parts[1].strip()

                    posted_at = None
                    if entry.get("published"):
                        try:
                            posted_at = parsedate_to_datetime(entry["published"]).replace(tzinfo=None)
                        except (ValueError, TypeError):
                            pass

                    link = entry.get("link", "")
                    external_id = f"wwr-{hash(link)}"

                    jobs.append(
                        RawJob(
                            external_id=external_id,
                            source=self.source_name,
                            title=title,
                            company=company,
                            url=link,
                            description=entry.get("summary", ""),
                            location="Remote",
                            posted_at=posted_at,
                        )
                    )
        return jobs
