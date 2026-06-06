"""Find hiring manager and employee emails via Hunter.io."""

import logging
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class Contact:
    name: str
    email: str
    title: str
    confidence: int = 0


class EmailFinder:
    hunter_base = "https://api.hunter.io/v2"

    async def find_contacts(self, company: str, domain: str, job_title: str, limit: int = 5) -> list[Contact]:
        if not settings.hunter_api_key:
            logger.warning("Hunter.io API key not configured")
            return self._fallback_contacts(company, domain, limit)

        domain = self._normalize_domain(domain, company)
        if not domain:
            return []

        contacts: list[Contact] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            domain_contacts = await self._domain_search(client, domain, limit)
            contacts.extend(domain_contacts)

            if len(contacts) < limit:
                dept_contacts = await self._department_search(client, domain, job_title, limit - len(contacts))
                contacts.extend(dept_contacts)

        seen = set()
        unique: list[Contact] = []
        for c in contacts:
            if c.email not in seen:
                seen.add(c.email)
                unique.append(c)
        return unique[:limit]

    async def _domain_search(self, client: httpx.AsyncClient, domain: str, limit: int) -> list[Contact]:
        try:
            response = await client.get(
                f"{self.hunter_base}/domain-search",
                params={
                    "domain": domain,
                    "api_key": settings.hunter_api_key,
                    "limit": limit,
                },
            )
            response.raise_for_status()
            data = response.json().get("data", {})
            emails = data.get("emails", [])

            hiring_keywords = ["hr", "recruit", "talent", "hiring", "people", "human resources"]
            prioritized = []
            others = []
            for e in emails:
                contact = Contact(
                    name=f"{e.get('first_name', '')} {e.get('last_name', '')}".strip(),
                    email=e.get("value", ""),
                    title=e.get("position") or "",
                    confidence=e.get("confidence", 0),
                )
                title_lower = contact.title.lower()
                if any(kw in title_lower for kw in hiring_keywords):
                    prioritized.append(contact)
                else:
                    others.append(contact)
            return (prioritized + others)[:limit]
        except Exception as exc:
            logger.error("Hunter domain search failed for %s: %s", domain, exc)
            return []

    async def _department_search(
        self, client: httpx.AsyncClient, domain: str, job_title: str, limit: int
    ) -> list[Contact]:
        department = self._infer_department(job_title)
        try:
            response = await client.get(
                f"{self.hunter_base}/domain-search",
                params={
                    "domain": domain,
                    "department": department,
                    "api_key": settings.hunter_api_key,
                    "limit": limit,
                },
            )
            response.raise_for_status()
            emails = response.json().get("data", {}).get("emails", [])
            return [
                Contact(
                    name=f"{e.get('first_name', '')} {e.get('last_name', '')}".strip(),
                    email=e.get("value", ""),
                    title=e.get("position") or "",
                    confidence=e.get("confidence", 0),
                )
                for e in emails[:limit]
            ]
        except Exception as exc:
            logger.error("Hunter department search failed: %s", exc)
            return []

    @staticmethod
    def _normalize_domain(domain: str, company: str) -> str:
        if domain and "." in domain:
            return domain.lower().strip()
        if company:
            clean = company.lower().replace(" ", "").replace(",", "").replace(".", "")
            return f"{clean}.com"
        return ""

    @staticmethod
    def _infer_department(job_title: str) -> str:
        title_lower = job_title.lower()
        if any(kw in title_lower for kw in ["engineer", "developer", "devops", "software"]):
            return "engineering"
        if any(kw in title_lower for kw in ["design", "ux", "ui"]):
            return "design"
        if any(kw in title_lower for kw in ["market", "sales", "business"]):
            return "sales"
        return "executive"

    @staticmethod
    def _fallback_contacts(company: str, domain: str, limit: int) -> list[Contact]:
        domain = domain or f"{company.lower().replace(' ', '')}.com"
        return [
            Contact(name="HR Team", email=f"careers@{domain}", title="Human Resources"),
            Contact(name="Recruiting", email=f"jobs@{domain}", title="Recruiting"),
            Contact(name="Talent", email=f"talent@{domain}", title="Talent Acquisition"),
        ][:limit]
