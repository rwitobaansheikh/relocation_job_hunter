"""Find hiring manager and employee emails via RocketReach API."""

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
    rocketreach_base = "https://api.rocketreach.co/api/v2"

    async def find_contacts(self, company: str, domain: str, job_title: str, limit: int = 5) -> list[Contact]:
        if not settings.rocketreach_api_key:
            logger.warning("RocketReach API key not configured")
            return self._fallback_contacts(company, domain, limit)

        domain = self._normalize_domain(domain, company)
        if not domain:
            return []

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Search for profiles matching HR / Recruiting at the target company
            search_url = f"{self.rocketreach_base}/person/search"
            headers = {
                "Api-Key": settings.rocketreach_api_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "query": {
                    "current_employer": [domain, company],
                    "current_title": ["hr", "human resources", "recruiter", "talent acquisition", "hiring"]
                }
            }

            try:
                await rate_limiter.acquire("rocketreach")
                response = await client.post(search_url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                # RocketReach sometimes returns profiles at the root or within 'profiles' key
                profiles = data.get("profiles", data) if isinstance(data, dict) else data
                if not isinstance(profiles, list):
                    profiles = []
            except Exception as exc:
                logger.error("RocketReach person search failed for %s: %s", domain, exc)
                profiles = []

            # 2. Look up contact info for the top candidates
            contacts: list[Contact] = []
            seen_emails = set()
            
            for profile in profiles:
                if len(contacts) >= limit:
                    break
                
                person_id = profile.get("id")
                if not person_id:
                    continue

                try:
                    await rate_limiter.acquire("rocketreach")
                    lookup_url = f"{self.rocketreach_base}/person/lookup"
                    lookup_resp = await client.get(lookup_url, params={"id": person_id}, headers=headers)
                    lookup_resp.raise_for_status()
                    person_data = lookup_resp.json()
                    
                    emails = person_data.get("emails", [])
                    name = person_data.get("name") or profile.get("name") or "Hiring Team"
                    title = person_data.get("current_title") or profile.get("current_title") or "Recruiter"
                    
                    # Prefer professional, valid emails
                    best_email = None
                    for e in emails:
                        # Sometimes valid is a string "true" or boolean True
                        is_valid = str(e.get("valid", "")).lower() == "true" or str(e.get("smtp_valid", "")).lower() == "valid"
                        if e.get("type") == "professional" and is_valid:
                            best_email = e.get("email")
                            break
                            
                    # Fallback to any professional email, then any valid email, then just first email
                    if not best_email and emails:
                        for e in emails:
                            if e.get("type") == "professional":
                                best_email = e.get("email")
                                break
                        if not best_email:
                            best_email = emails[0].get("email")
                            
                    if best_email and best_email not in seen_emails:
                        seen_emails.add(best_email)
                        contacts.append(Contact(
                            name=name,
                            email=best_email,
                            title=title,
                            confidence=90  # RocketReach verified
                        ))
                except Exception as exc:
                    logger.warning("RocketReach lookup failed for ID %s: %s", person_id, exc)

        # Last resort: if RocketReach API failed or found nothing, fall back to generic role addresses
        if not contacts:
            logger.info("No verified contacts from RocketReach for %s, using generic role addresses", domain)
            return self._fallback_contacts(company, domain, limit)
            
        return contacts[:limit]

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