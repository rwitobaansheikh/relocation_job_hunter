"""Self-hosted HR/recruiting email scraper (no paid APIs).

Accepts a company name, website/domain, or job posting URL and returns 3–6
contacts belonging to recruiters, HR, or talent/careers teams.

Sources (merged and de-duplicated):
  1. Company website — careers/contact pages, mailto links, internal crawl
  2. Job posting page — emails embedded in the listing
  3. Web search (DuckDuckGo HTML) — snippets and result pages
  4. LLM agent — resolve domain, classify contacts, suggest role inboxes
  5. Pattern fallbacks — careers@, jobs@, talent@ when nothing else is found
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.services.llm import llm_available, llm_generate
from app.services.url_importer import _is_job_board, _registrable_domain, import_job_from_url

logger = logging.getLogger(__name__)

MIN_CONTACTS = 3
MAX_CONTACTS = 6

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

_HR_LOCAL_PARTS = frozenset({
    "hr", "careers", "jobs", "talent", "recruiting", "recruitment", "recruit",
    "hiring", "people", "peopleops", "people-ops", "apply", "applications",
    "staffing", "employment", "join", "joinus", "workwithus", "humanresources",
    "talentacquisition", "talent-acquisition", "campus", "university",
})

_HR_TITLE_KEYWORDS = (
    "hr", "human resources", "recruit", "recruiting", "recruiter", "talent",
    "people", "hiring", "careers", "talent acquisition", "staffing",
    "employment", "people operations", "people ops", "campus", "university",
)

_CAREERS_PATHS = (
    "/careers", "/jobs", "/join-us", "/join", "/work-with-us", "/contact",
    "/about", "/team", "/recruiting", "/talent", "/hiring", "/opportunities",
    "/open-positions", "/vacancies", "/work-here", "/life-at", "/people",
)

_CAREERS_LINK_KEYWORDS = (
    "career", "job", "hiring", "talent", "recruit", "join", "work-with",
    "opportunit", "vacanc", "apply",
)

_GENERIC_ROLE_EMAILS = (
    ("HR Team", "careers", "Human Resources"),
    ("Recruiting", "jobs", "Recruiting"),
    ("Talent Acquisition", "talent", "Talent Acquisition"),
    ("People Team", "people", "People Operations"),
    ("Hiring Team", "hiring", "Hiring"),
    ("Recruitment", "recruitment", "Recruitment"),
)

_FREE_EMAIL_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
    "protonmail.com", "aol.com", "live.com", "me.com",
})

_SKIP_HOSTS = frozenset({
    "facebook.com", "twitter.com", "x.com", "instagram.com", "youtube.com",
    "linkedin.com", "wikipedia.org", "crunchbase.com", "glassdoor.com",
    "indeed.com", "google.com", "bing.com", "duckduckgo.com",
})


@dataclass
class Contact:
    name: str
    email: str
    title: str
    confidence: int = 0


@dataclass
class ResolvedCompany:
    company: str = ""
    domain: str = ""
    job_title: str = ""
    source_url: str = ""


@dataclass
class ScrapedEmail:
    email: str
    name: str = ""
    title: str = ""
    source: str = ""
    score: int = 0


@dataclass
class EmailScrapeResult:
    company: str = ""
    domain: str = ""
    contacts: list[Contact] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    message: str = ""


class EmailScraper:
    def __init__(self) -> None:
        self._max_pages = 18

    async def find_recruiting_emails(
        self,
        *,
        company: str = "",
        website: str = "",
        job_url: str = "",
        min_contacts: int = MIN_CONTACTS,
        max_contacts: int = MAX_CONTACTS,
    ) -> EmailScrapeResult:
        """Find 3–6 HR/recruiting emails for a company."""
        min_contacts = max(1, min(min_contacts, max_contacts))
        max_contacts = min(MAX_CONTACTS, max(min_contacts, max_contacts))

        resolved = await self._resolve_input(company, website, job_url)
        if not resolved.domain and resolved.company:
            resolved.domain = await self._discover_domain(resolved.company)

        if not resolved.domain and not resolved.company:
            return EmailScrapeResult(
                message="Could not determine company or domain from the input provided.",
            )

        domain = resolved.domain or self._guess_domain(resolved.company)
        sources_used: list[str] = []
        candidates: list[ScrapedEmail] = []

        # Source 1: job posting page
        if resolved.source_url:
            job_emails = await self._scrape_url(resolved.source_url, domain, "job_posting")
            if job_emails:
                sources_used.append("job_posting")
                candidates.extend(job_emails)

        # Source 2: company website
        site_emails = await self._scrape_company_site(domain)
        if site_emails:
            sources_used.append("website")
            candidates.extend(site_emails)

        # Source 3: web search (DuckDuckGo)
        search_emails = await self._search_web_for_emails(resolved.company, domain)
        if search_emails:
            sources_used.append("search")
            candidates.extend(search_emails)

        # Source 4: AI agent — classify, rank, discover extras
        if llm_available():
            if not candidates or len(candidates) < min_contacts:
                ai_suggested = await self._ai_discover_emails(
                    resolved.company, domain, resolved.job_title, candidates
                )
                if ai_suggested:
                    sources_used.append("ai_discover")
                    candidates.extend(ai_suggested)

            if candidates:
                sources_used.append("ai")
                candidates = await self._ai_rank_and_filter(
                    candidates, resolved.company, domain, resolved.job_title
                )
        else:
            candidates = self._heuristic_rank(candidates)

        contacts = self._to_contacts(candidates, max_contacts)

        if len(contacts) < min_contacts:
            if "fallback" not in sources_used:
                sources_used.append("fallback")
            contacts = self._pad_with_generic(contacts, domain, min_contacts, max_contacts)

        contacts = contacts[:max_contacts]

        message = ""
        if len(contacts) < min_contacts:
            message = (
                f"Only found {len(contacts)} contact(s). "
                "Try providing the company website or a direct job link."
            )
        elif not any(s in sources_used for s in ("website", "search", "job_posting")):
            message = (
                "Could not scrape live emails; showing likely recruiting inboxes "
                "for this domain. Verify before sending."
            )

        return EmailScrapeResult(
            company=resolved.company,
            domain=domain,
            contacts=contacts,
            sources_used=sources_used,
            message=message,
        )

    async def _resolve_input(
        self, company: str, website: str, job_url: str
    ) -> ResolvedCompany:
        company = (company or "").strip()
        website = (website or "").strip()
        job_url = (job_url or "").strip()

        if job_url:
            if not job_url.lower().startswith(("http://", "https://")):
                job_url = "https://" + job_url
            imported = await import_job_from_url(job_url)
            return ResolvedCompany(
                company=company or imported.get("company", ""),
                domain=self._normalize_domain(website) or imported.get("company_domain", ""),
                job_title=imported.get("title", ""),
                source_url=job_url,
            )

        domain = self._normalize_domain(website)
        if domain and not company:
            company = self._company_from_domain(domain)
        elif company and not domain:
            domain = ""

        return ResolvedCompany(company=company, domain=domain)

    async def _discover_domain(self, company: str) -> str:
        """Use web search + heuristics to find the company's website."""
        results = await self._duckduckgo_search(f"{company} official website", max_results=8)
        for url in results:
            host = urlparse(url).netloc.lower()
            if not host or _is_job_board(host):
                continue
            reg = _registrable_domain(host)
            if reg in _SKIP_HOSTS:
                continue
            # Prefer domains that resemble the company name
            slug = re.sub(r"[^a-z0-9]", "", company.lower())
            host_slug = reg.split(".")[0]
            if slug and (slug in host_slug or host_slug in slug):
                return reg
            return reg

        # Try common TLD patterns
        slug = re.sub(r"[^a-z0-9]", "", company.lower())
        if not slug:
            return ""
        for tld in ("com", "io", "co", "co.uk", "ai"):
            candidate = f"{slug}.{tld}"
            if await self._domain_reachable(candidate):
                return candidate
        return f"{slug}.com"

    async def _domain_reachable(self, domain: str) -> bool:
        try:
            async with httpx.AsyncClient(
                timeout=6.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
            ) as client:
                resp = await client.head(f"https://{domain}")
                return resp.status_code < 500
        except Exception:
            return False

    async def _scrape_company_site(self, domain: str) -> list[ScrapedEmail]:
        if not domain:
            return []

        base_url = f"https://{domain}"
        seed_urls = [base_url] + [urljoin(base_url, p) for p in _CAREERS_PATHS]

        # Try sitemap for careers URLs
        sitemap_urls = await self._fetch_sitemap_urls(domain)
        seed_urls.extend(sitemap_urls[:10])

        found: dict[str, ScrapedEmail] = {}
        visited: set[str] = set()
        queue = list(dict.fromkeys(seed_urls))  # de-dupe, preserve order

        async with httpx.AsyncClient(
            timeout=12.0,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            while queue and len(visited) < self._max_pages:
                url = queue.pop(0)
                norm = url.rstrip("/")
                if norm in visited:
                    continue
                visited.add(norm)

                try:
                    resp = await client.get(url)
                    if resp.status_code >= 400:
                        continue
                    page_emails = self._extract_emails_from_html(
                        resp.text, url, domain
                    )
                    for item in page_emails:
                        key = item.email.lower()
                        if key not in found or item.score > found[key].score:
                            found[key] = item

                    # Follow careers-related internal links (one hop from seed pages)
                    if len(visited) <= 6:
                        for link in self._careers_links(resp.text, base_url, domain):
                            if link not in visited and link not in queue:
                                queue.append(link)
                except Exception as exc:
                    logger.debug("Website scrape failed for %s: %s", url, exc)

        return list(found.values())

    async def _fetch_sitemap_urls(self, domain: str) -> list[str]:
        urls: list[str] = []
        sitemap_url = f"https://{domain}/sitemap.xml"
        try:
            async with httpx.AsyncClient(
                timeout=8.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
            ) as client:
                resp = await client.get(sitemap_url)
                if resp.status_code >= 400:
                    return []
                for loc in re.findall(r"<loc>([^<]+)</loc>", resp.text, re.I):
                    if any(kw in loc.lower() for kw in _CAREERS_LINK_KEYWORDS):
                        urls.append(loc.strip())
        except Exception:
            pass
        return urls

    def _careers_links(self, html: str, base_url: str, domain: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        out: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            full = urljoin(base_url, href)
            parsed = urlparse(full)
            if _registrable_domain(parsed.netloc) != domain:
                continue
            path = (parsed.path + " " + a.get_text(" ", strip=True)).lower()
            if any(kw in path for kw in _CAREERS_LINK_KEYWORDS):
                out.append(full.split("#")[0])
        return out[:8]

    async def _scrape_url(
        self, url: str, domain: str, source_label: str
    ) -> list[ScrapedEmail]:
        try:
            async with httpx.AsyncClient(
                timeout=12.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT}
            ) as client:
                resp = await client.get(url)
                if resp.status_code >= 400:
                    return []
                return self._extract_emails_from_html(resp.text, url, domain, source_label)
        except Exception as exc:
            logger.debug("URL scrape failed for %s: %s", url, exc)
            return []

    async def _search_web_for_emails(
        self, company: str, domain: str
    ) -> list[ScrapedEmail]:
        queries = [
            f'site:{domain} (careers OR recruiting OR talent OR hr) email',
            f'"{company}" recruiting email @{domain}' if company else "",
            f'"{company}" careers contact email' if company else "",
        ]
        found: dict[str, ScrapedEmail] = {}

        for query in queries:
            if not query.strip():
                continue
            result_urls = await self._duckduckgo_search(query, max_results=6)
            # Extract emails from search result snippets
            snippets = await self._duckduckgo_snippets(query)
            for text in snippets:
                for addr in _EMAIL_RE.findall(text):
                    addr = addr.lower()
                    if self._is_valid_company_email(addr, domain):
                        item = ScrapedEmail(
                            email=addr,
                            source="search_snippet",
                            score=self._score_email(addr, text, query),
                        )
                        key = addr
                        if key not in found or item.score > found[key].score:
                            found[key] = item

            # Scrape top result pages (limited)
            for url in result_urls[:4]:
                if _registrable_domain(urlparse(url).netloc) in _SKIP_HOSTS:
                    continue
                page_emails = await self._scrape_url(url, domain, "search_page")
                for item in page_emails:
                    key = item.email.lower()
                    if key not in found or item.score > found[key].score:
                        found[key] = item
            await asyncio.sleep(0.4)  # polite pause between searches

        return list(found.values())

    async def _duckduckgo_search(self, query: str, max_results: int = 6) -> list[str]:
        urls: list[str] = []
        try:
            async with httpx.AsyncClient(
                timeout=12.0,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                resp = await client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query, "b": "", "kl": ""},
                )
                if resp.status_code >= 400:
                    return []
                soup = BeautifulSoup(resp.text, "lxml")
                for a in soup.select("a.result__a"):
                    href = a.get("href", "")
                    if not href:
                        continue
                    # DDG wraps links: //duckduckgo.com/l/?uddg=...
                    if "uddg=" in href:
                        from urllib.parse import unquote, parse_qs, urlparse as up
                        parsed = up(href)
                        qs = parse_qs(parsed.query)
                        if "uddg" in qs:
                            href = unquote(qs["uddg"][0])
                    if href.startswith("http"):
                        urls.append(href)
                    if len(urls) >= max_results:
                        break
        except Exception as exc:
            logger.debug("DuckDuckGo search failed: %s", exc)
        return urls

    async def _duckduckgo_snippets(self, query: str) -> list[str]:
        snippets: list[str] = []
        try:
            async with httpx.AsyncClient(
                timeout=12.0,
                follow_redirects=True,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                resp = await client.post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query},
                )
                soup = BeautifulSoup(resp.text, "lxml")
                for snip in soup.select(".result__snippet"):
                    text = snip.get_text(" ", strip=True)
                    if text:
                        snippets.append(text)
        except Exception:
            pass
        return snippets

    def _extract_emails_from_html(
        self, html: str, page_url: str, domain: str, source_label: str = "web"
    ) -> list[ScrapedEmail]:
        soup = BeautifulSoup(html, "lxml")
        results: list[ScrapedEmail] = []
        path = urlparse(page_url).path or "/"

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.lower().startswith("mailto:"):
                continue
            addr = href[7:].split("?")[0].strip()
            if self._is_valid_company_email(addr, domain):
                label = a.get_text(strip=True) or ""
                results.append(
                    ScrapedEmail(
                        email=addr.lower(),
                        name=label if "@" not in label else "",
                        title=label,
                        source=f"{source_label}:{path}",
                        score=self._score_email(addr, label, page_url),
                    )
                )

        # Also scan raw HTML for obfuscated emails (e.g. careers [at] company dot com)
        deobfuscated = self._deobfuscate_emails(html)
        text = soup.get_text(" ", strip=True) + " " + deobfuscated
        for match in _EMAIL_RE.findall(text):
            addr = match.lower()
            if self._is_valid_company_email(addr, domain):
                results.append(
                    ScrapedEmail(
                        email=addr,
                        source=f"{source_label}:{path}",
                        score=self._score_email(addr, "", page_url),
                    )
                )

        return results

    @staticmethod
    def _deobfuscate_emails(text: str) -> str:
        """Normalize common obfuscation patterns to extractable emails."""
        t = text
        t = re.sub(
            r"([A-Za-z0-9._%+\-]+)\s*[\[\(]?\s*(?:at|@)\s*[\]\)]?\s*"
            r"([A-Za-z0-9.\-]+)\s*[\[\(]?\s*(?:dot|\.)\s*[\]\)]?\s*([A-Za-z]{2,})",
            r"\1@\2.\3",
            t,
            flags=re.I,
        )
        return t

    def _score_email(self, email: str, context: str, page_url: str) -> int:
        local = email.split("@")[0].lower()
        ctx = f"{local} {context} {page_url}".lower()
        score = 10

        if any(kw in local for kw in _HR_LOCAL_PARTS):
            score += 60
        if any(kw in ctx for kw in _HR_TITLE_KEYWORDS):
            score += 30
        if any(p in page_url.lower() for p in ("career", "job", "hiring", "talent", "recruit")):
            score += 20
        if local in ("info", "contact", "hello", "support", "sales", "admin", "noreply"):
            score -= 40

        return max(0, min(100, score))

    def _heuristic_rank(self, candidates: list[ScrapedEmail]) -> list[ScrapedEmail]:
        hr_only = [c for c in candidates if self._is_hr_related(c.email, c.title)]
        hr_only.sort(key=lambda c: c.score, reverse=True)
        return hr_only

    async def _ai_discover_emails(
        self,
        company: str,
        domain: str,
        job_title: str,
        existing: list[ScrapedEmail],
    ) -> list[ScrapedEmail]:
        """Ask the LLM for likely recruiting inboxes when scraping found too few."""
        existing_list = [c.email for c in existing]
        prompt = (
            f"Company: {company}\nDomain: {domain}\nJob: {job_title or 'unknown'}\n"
            f"Already found: {existing_list or 'none'}\n\n"
            "Suggest 3-6 plausible professional recruiting/HR email addresses for this company. "
            "Prefer generic team inboxes (careers@, talent@, jobs@) and publicly known patterns. "
            "Do NOT invent personal names unless you are highly confident they are real public contacts.\n"
            'Return JSON only: {"contacts":[{"email":"...","name":"...","title":"...","confidence":0-100}]}'
        )
        try:
            raw = await llm_generate(
                prompt,
                system=(
                    "You help job seekers find recruiting contact emails. "
                    "Only suggest realistic professional addresses on the given domain. JSON only."
                ),
                temperature=0.3,
                max_tokens=1024,
                json_mode=True,
            )
            data = self._parse_json(raw)
            out: list[ScrapedEmail] = []
            for item in data.get("contacts", []):
                email = (item.get("email") or "").strip().lower()
                if not email or not self._is_valid_company_email(email, domain):
                    continue
                out.append(
                    ScrapedEmail(
                        email=email,
                        name=(item.get("name") or "").strip(),
                        title=(item.get("title") or "Recruiting / HR").strip(),
                        source="ai_suggest",
                        score=int(item.get("confidence") or 25),
                    )
                )
            return out
        except Exception as exc:
            logger.warning("AI email discovery failed: %s", exc)
            return []

    async def _ai_rank_and_filter(
        self,
        candidates: list[ScrapedEmail],
        company: str,
        domain: str,
        job_title: str,
    ) -> list[ScrapedEmail]:
        if not candidates:
            return []

        payload = [
            {
                "email": c.email,
                "name": c.name,
                "title": c.title,
                "source": c.source,
                "score": c.score,
            }
            for c in candidates
        ]
        prompt = (
            f"Company: {company or domain}\n"
            f"Domain: {domain}\n"
            f"Job title context: {job_title or 'unknown'}\n\n"
            "Candidates:\n"
            f"{json.dumps(payload, indent=2)}\n\n"
            "Return JSON only: "
            '{"contacts":[{"email":"...","name":"...","title":"...","relevance":0-100,"is_recruiting":true}]} '
            "Include ONLY recruiting/HR/talent/careers contacts (is_recruiting=true). "
            "Sort by relevance descending. Drop sales, support, info@, noreply, and personal non-HR emails."
        )
        try:
            raw = await llm_generate(
                prompt,
                system=(
                    "You are an expert recruiter contact researcher. "
                    "Filter and rank professional recruiting contacts. Respond with valid JSON only."
                ),
                temperature=0.2,
                max_tokens=2048,
                json_mode=True,
            )
            data = self._parse_json(raw)
            ranked: list[ScrapedEmail] = []
            seen: set[str] = set()
            for item in data.get("contacts", []):
                email = (item.get("email") or "").strip().lower()
                if not email or email in seen:
                    continue
                if not item.get("is_recruiting", True):
                    continue
                seen.add(email)
                ranked.append(
                    ScrapedEmail(
                        email=email,
                        name=(item.get("name") or "").strip(),
                        title=(item.get("title") or "").strip(),
                        source="ai",
                        score=int(item.get("relevance") or 50),
                    )
                )
            if ranked:
                return ranked
        except Exception as exc:
            logger.warning("AI contact ranking failed: %s", exc)

        return self._heuristic_rank(candidates)

    @staticmethod
    def _parse_json(raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        return json.loads(text)

    def _to_contacts(self, candidates: list[ScrapedEmail], limit: int) -> list[Contact]:
        seen: set[str] = set()
        out: list[Contact] = []
        for c in candidates:
            key = c.email.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(
                Contact(
                    name=c.name or self._name_from_email(c.email),
                    email=c.email,
                    title=c.title or "Recruiting / HR",
                    confidence=c.score,
                )
            )
            if len(out) >= limit:
                break
        return out

    def _pad_with_generic(
        self,
        contacts: list[Contact],
        domain: str,
        min_contacts: int,
        max_contacts: int,
    ) -> list[Contact]:
        seen = {c.email.lower() for c in contacts}
        for name, local, title in _GENERIC_ROLE_EMAILS:
            if len(contacts) >= min_contacts:
                break
            email = f"{local}@{domain}"
            if email.lower() in seen:
                continue
            seen.add(email.lower())
            contacts.append(Contact(name=name, email=email, title=title, confidence=20))
        return contacts[:max_contacts]

    @staticmethod
    def _is_hr_related(email: str, title: str = "") -> bool:
        local = email.split("@")[0].lower()
        blob = f"{local} {title}".lower()
        if any(kw in blob for kw in _HR_TITLE_KEYWORDS):
            return True
        if any(part in local for part in _HR_LOCAL_PARTS):
            return True
        if "." in local or "_" in local:
            return any(kw in blob for kw in _HR_TITLE_KEYWORDS)
        return False

    @staticmethod
    def _is_valid_company_email(email: str, domain: str) -> bool:
        email = email.lower().strip()
        if not _EMAIL_RE.fullmatch(email):
            return False
        parts = email.split("@")
        if len(parts) != 2:
            return False
        local, host = parts
        if host in _FREE_EMAIL_DOMAINS:
            return False
        if any(x in local for x in ("noreply", "no-reply", "donotreply", "bounce")):
            return False
        if domain and not (host == domain or host.endswith("." + domain)):
            return False
        return True

    @staticmethod
    def _normalize_domain(value: str) -> str:
        value = (value or "").strip().lower()
        if not value:
            return ""
        if "@" in value:
            value = value.split("@", 1)[1]
        if "://" in value:
            value = urlparse(value).netloc
        if value.startswith("www."):
            value = value[4:]
        value = value.split("/")[0].split(":")[0]
        if "." not in value:
            return ""
        return _registrable_domain(value)

    @staticmethod
    def _guess_domain(company: str) -> str:
        clean = re.sub(r"[^a-z0-9]", "", company.lower())
        return f"{clean}.com" if clean else ""

    @staticmethod
    def _company_from_domain(domain: str) -> str:
        base = domain.split(".")[0]
        return base.replace("-", " ").title()

    @staticmethod
    def _name_from_email(email: str) -> str:
        local = email.split("@")[0]
        if "." in local:
            parts = local.replace("_", ".").split(".")
            return " ".join(p.capitalize() for p in parts if p)
        return local.replace("-", " ").replace("_", " ").title()
