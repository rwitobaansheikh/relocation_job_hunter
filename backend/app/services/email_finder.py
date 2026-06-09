"""Find hiring manager and employee emails via Hunter.io."""

import logging
from dataclasses import dataclass

import httpx

from app.config import settings
from app.services import rate_limiter

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

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Priority order: HR first, then IT, then any department so we still
            # surface contacts for roles where neither HR nor IT is published.
            contacts = await self._department_search(client, domain, "hr", limit)
            if not contacts:
                logger.info("No HR contacts for %s, trying IT department", domain)
                contacts = await self._department_search(client, domain, "it", limit)
            if not contacts:
                logger.info("No HR/IT contacts for %s, trying unfiltered domain search", domain)
                contacts = await self._domain_search(client, domain, limit)

        seen = set()
        unique: list[Contact] = []
        for c in contacts:
            if c.email and c.email not in seen:
                seen.add(c.email)
                unique.append(c)

        verified = await self._filter_verified(unique)
        # Last resort: if Hunter has the domain but everything got filtered out
        # (or returned nothing), fall back to generic role addresses so the user
        # always has someone to contact.
        if not verified:
            logger.info("No verified contacts for %s, using generic role addresses", domain)
            return self._fallback_contacts(company, domain, limit)
        return verified[:limit]

    async def _filter_verified(self, contacts: list[Contact]) -> list[Contact]:
        """Drop addresses Hunter flags as undeliverable. Keeps unknown/risky ones."""
        if not contacts:
            return contacts
        async with httpx.AsyncClient(timeout=30.0) as client:
            kept: list[Contact] = []
            for c in contacts:
                status = await self._verify_email(client, c.email)
                if status == "undeliverable":
                    logger.info("Skipping undeliverable address %s", c.email)
                    continue
                kept.append(c)
        return kept

    async def _verify_email(self, client: httpx.AsyncClient, email: str) -> str:
        try:
            await rate_limiter.acquire("hunter")
            response = await client.get(
                f"{self.hunter_base}/email-verifier",
                params={"email": email, "api_key": settings.hunter_api_key},
            )
            response.raise_for_status()
            return response.json().get("data", {}).get("status", "unknown")
        except Exception as exc:
            logger.warning("Email verification failed for %s: %s", email, exc)
            return "unknown"

    async def _domain_search(
        self, client: httpx.AsyncClient, domain: str, limit: int
    ) -> list[Contact]:
        """Unfiltered domain search, prioritizing hiring-related titles."""
        try:
            await rate_limiter.acquire("hunter")
            response = await client.get(
                f"{self.hunter_base}/domain-search",
                params={
                    "domain": domain,
                    "api_key": settings.hunter_api_key,
                    "limit": limit,
                },
            )
            response.raise_for_status()
            emails = response.json().get("data", {}).get("emails", [])

            hiring_keywords = ["hr", "recruit", "talent", "hiring", "people", "human resources"]
            prioritized: list[Contact] = []
            others: list[Contact] = []
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
        self, client: httpx.AsyncClient, domain: str, department: str, limit: int
    ) -> list[Contact]:
        try:
            await rate_limiter.acquire("hunter")
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
    def _fallback_contacts(company: str, domain: str, limit: int) -> list[Contact]:
        domain = domain or f"{company.lower().replace(' ', '')}.com"
        return [
            Contact(name="HR Team", email=f"careers@{domain}", title="Human Resources"),
            Contact(name="Recruiting", email=f"jobs@{domain}", title="Recruiting"),
            Contact(name="Talent", email=f"talent@{domain}", title="Talent Acquisition"),
        ][:limit]
