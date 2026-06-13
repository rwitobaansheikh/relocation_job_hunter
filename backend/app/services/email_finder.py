"""Find hiring manager and employee emails via RocketReach API."""

import logging
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

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
        domain = self._normalize_domain(domain, company)
        if not domain:
            return []

        contacts = []
        if settings.rocketreach_api_key:
            contacts = await self._search_rocketreach(company, domain, limit)

        if not contacts:
            logger.info("RocketReach API failed or returned 0 contacts. Falling back to OSINT web scraping...")
            contacts = await self._search_osint(company, domain, limit)

        # Last resort: if everything failed, fall back to generic role addresses
        if not contacts:
            logger.info("No contacts found from OSINT, using generic role addresses")
            return self._fallback_contacts(company, domain, limit)
            
        return contacts[:limit]

    async def _search_rocketreach(self, company: str, domain: str, limit: int) -> list[Contact]:
        contacts: list[Contact] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
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
                if response.status_code == 401:
                    logger.error("RocketReach API Key is unauthorized (401).")
                    return []
                response.raise_for_status()
                data = response.json()
                profiles = data.get("profiles", data) if isinstance(data, dict) else data
                if not isinstance(profiles, list):
                    profiles = []
            except Exception as exc:
                logger.error("RocketReach person search failed for %s: %s", domain, exc)
                return []

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
                    
                    best_email = None
                    for e in emails:
                        is_valid = str(e.get("valid", "")).lower() == "true" or str(e.get("smtp_valid", "")).lower() == "valid"
                        if e.get("type") == "professional" and is_valid:
                            best_email = e.get("email")
                            break
                    if not best_email and emails:
                        for e in emails:
                            if e.get("type") == "professional":
                                best_email = e.get("email")
                                break
                        if not best_email:
                            best_email = emails[0].get("email")
                            
                    if best_email and best_email not in seen_emails:
                        seen_emails.add(best_email)
                        contacts.append(Contact(name=name, email=best_email, title=title, confidence=90))
                except Exception as exc:
                    logger.warning("RocketReach lookup failed for ID %s: %s", person_id, exc)

        return contacts

    async def _search_osint(self, company: str, domain: str, limit: int) -> list[Contact]:
        contacts: list[Contact] = []
        seen_emails = set()
        
        queries = [
            f'site:linkedin.com/in/ "HR" "{company}"',
            f'site:linkedin.com/in/ "Recruiter" "{company}"',
            f'site:linkedin.com/in/ "Talent Acquisition" "{company}"'
        ]
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            for query in queries:
                if len(contacts) >= limit:
                    break
                
                try:
                    res = await client.post("https://html.duckduckgo.com/html/", data={"q": query}, headers=headers)
                    if res.status_code != 200:
                        continue
                        
                    soup = BeautifulSoup(res.text, "html.parser")
                    results = soup.select(".result__body")
                    
                    for r in results:
                        if len(contacts) >= limit:
                            break
                            
                        title_el = r.select_one(".result__title a")
                        if not title_el:
                            continue
                            
                        title_text = title_el.get_text(strip=True)
                        # Remove trailing LinkedIn tag
                        title_text = re.sub(r'\s*\|\s*LinkedIn.*$', '', title_text, flags=re.IGNORECASE)
                        
                        # Split by hyphens. Usually "Jane Doe - Technical Recruiter - Stripe"
                        parts = [p.strip() for p in title_text.split('-')]
                        if not parts:
                            continue
                            
                        name = parts[0].strip()
                        job_title = parts[1].strip() if len(parts) > 1 else "Recruiter"
                        
                        # Skip if name looks like a generic title
                        if len(name.split()) > 4 or any(keyword in name.lower() for keyword in ["jobs", "careers", "hiring", "recruiting"]):
                            continue
                        
                        # Generate email
                        clean_name = re.sub(r'[^a-zA-Z\s]', '', name).strip().lower()
                        name_parts = clean_name.split()
                        
                        if len(name_parts) >= 2:
                            first = name_parts[0]
                            last = name_parts[-1]
                            email = f"{first}.{last}@{domain}"
                        elif len(name_parts) == 1:
                            email = f"{name_parts[0]}@{domain}"
                        else:
                            continue
                            
                        if email not in seen_emails:
                            seen_emails.add(email)
                            contacts.append(Contact(name=name, email=email, title=job_title, confidence=60))
                            
                except Exception as exc:
                    logger.warning("OSINT search failed for query '%s': %s", query, exc)
                    
        return contacts

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