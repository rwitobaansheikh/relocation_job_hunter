"""Greenhouse job-board scraper.

Greenhouse has no global search API; each company exposes its own board at
boards-api.greenhouse.io. We fetch a configurable list of boards
(settings.greenhouse_boards) and filter client-side by the user's roles.
"""

import html as html_lib
import logging
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.scraper.base import RawJob

logger = logging.getLogger(__name__)


def _parse_iso(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None)
    except ValueError:
        return None


def _strip_html(content: str) -> str:
    if not content:
        return ""
    return BeautifulSoup(html_lib.unescape(content), "lxml").get_text(" ", strip=True)


def _matches_roles(title: str, text: str, roles: list[str]) -> bool:
    if not roles:
        return True
    title_l, text_l = title.lower(), text.lower()
    for role in roles:
        role_l = role.lower()
        if role_l in title_l or role_l in text_l:
            return True
        tokens = [t for t in role_l.split() if t]
        if tokens and all(tok in text_l for tok in tokens):
            return True
    return False


class GreenhouseScraper:
    source_name = "greenhouse"
    api_url = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"

    def _boards(self) -> list[str]:
        return [b.strip().lower() for b in (settings.greenhouse_boards or "").split(",") if b.strip()]

    async def fetch_jobs(self, limit: int = 100, roles: Optional[list[str]] = None) -> list[RawJob]:
        boards = self._boards()
        if not boards:
            return []
        roles = [r for r in (roles or []) if r]

        jobs: list[RawJob] = []
        seen: set[str] = set()
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                for board in boards:
                    if len(jobs) >= limit:
                        break
                    try:
                        response = await client.get(
                            self.api_url.format(board=board),
                            headers={"User-Agent": "relocation-job-hunter/1.0"},
                            params={"content": "true"},
                        )
                        if response.status_code != 200:
                            continue
                        data = response.json()
                    except Exception as exc:
                        logger.warning("Greenhouse board %s failed: %s", board, exc)
                        continue

                    for item in data.get("jobs", []):
                        if len(jobs) >= limit:
                            break
                        external_id = f"greenhouse-{board}-{item.get('id', '')}"
                        if external_id in seen:
                            continue

                        title = item.get("title") or "Unknown"
                        description = _strip_html(item.get("content") or "")
                        if not _matches_roles(title, f"{title} {description}", roles):
                            continue
                        seen.add(external_id)

                        location = ((item.get("location") or {}).get("name")) or ""
                        company = item.get("company_name") or board.replace("-", " ").title()
                        jobs.append(
                            RawJob(
                                external_id=external_id,
                                source=self.source_name,
                                title=title,
                                company=company,
                                url=item.get("absolute_url") or f"https://boards.greenhouse.io/{board}",
                                description=description,
                                location=location,
                                posted_at=_parse_iso(item.get("first_published") or item.get("updated_at")),
                                tags=[],
                            )
                        )
        except Exception as exc:
            logger.warning("Greenhouse scraper failed: %s", exc)
        return jobs
