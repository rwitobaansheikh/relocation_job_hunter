"""Suggest job-search criteria from the user's CV and cover letter."""

import json
import logging
import re
from typing import Any, Optional

from app.database import UserProfile
from app.schemas import SENIORITY_LEVELS
from app.services.llm import llm_generate, resolve_gemini_api_key

logger = logging.getLogger(__name__)

_VALID_SENIORITY = set(SENIORITY_LEVELS)
_VALID_POSTED = {24, 48, 168, 336}

_SYSTEM = (
    "You are an expert career coach and job-search strategist. Given a candidate's CV "
    "and cover letter, recommend search criteria that will surface the largest number of "
    "relevant job listings while staying truthful to their experience. Return JSON only."
)


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    return t.strip()


def _extract_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    cleaned = _strip_fences(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(cleaned[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except (ValueError, TypeError):
        return None


def _normalize_strings(raw: Any, limit: int = 10, max_len: int = 120) -> list[str]:
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        val = item.strip()
        key = val.lower()
        if val and key not in seen and len(val) <= max_len:
            seen.add(key)
            out.append(val)
        if len(out) >= limit:
            break
    return out


def _normalize_seniority(raw: Any) -> list[str]:
    levels = _normalize_strings(raw, limit=5, max_len=20)
    return [lvl for lvl in levels if lvl in _VALID_SENIORITY]


def _normalize_posted_hours(raw: Any) -> int:
    try:
        hours = int(raw)
    except (TypeError, ValueError):
        return 168
    if hours in _VALID_POSTED:
        return hours
    # Snap to nearest valid bucket.
    return min(_VALID_POSTED, key=lambda h: abs(h - hours))


def _normalize_salary(raw: Any) -> Optional[int]:
    if raw is None or raw == "":
        return None
    try:
        val = int(raw)
        return val if val >= 0 else None
    except (TypeError, ValueError):
        return None


def _default_criteria() -> dict:
    return {
        "roles": [],
        "locations": [],
        "seniority_levels": ["entry"],
        "posted_within_hours": 168,
        "min_salary": None,
        "max_salary": None,
        "summary": "",
    }


def _normalize_criteria(data: dict) -> dict:
    out = _default_criteria()
    out["roles"] = _normalize_strings(data.get("roles"), limit=8)
    out["locations"] = _normalize_strings(data.get("locations"), limit=12)
    seniority = _normalize_seniority(data.get("seniority_levels"))
    out["seniority_levels"] = seniority or ["entry"]
    out["posted_within_hours"] = _normalize_posted_hours(data.get("posted_within_hours"))
    out["min_salary"] = _normalize_salary(data.get("min_salary"))
    out["max_salary"] = _normalize_salary(data.get("max_salary"))
    summary = data.get("summary") or data.get("rationale") or ""
    out["summary"] = str(summary).strip()[:800]
    return out


async def suggest_search_criteria(profile: UserProfile) -> tuple[dict, str]:
    """Return (criteria dict, error message). Empty error means success."""
    cv = (profile.cv_text or "").strip()
    if not cv:
        return _default_criteria(), "Upload your CV first so we can analyze it."

    cover = (profile.baseline_cover_letter_text or "").strip()
    skills = (profile.skills or "").strip()
    summary = (profile.summary or "").strip()
    location = (profile.location or "").strip()

    prompt = f"""Analyze this candidate's CV and cover letter. Recommend job-search criteria
designed to return a HIGH VOLUME of relevant listings on LinkedIn and remote job boards.

Goals:
1. Maximize discoverable jobs without straying from what the candidate can credibly apply for.
2. Use multiple synonymous job titles recruiters actually post (5–8 titles).
3. Include ONLY broad locations: always add "Remote" when suitable; suggest ONLY country names (e.g. 'United Kingdom', 'Germany', 'Netherlands', 'Ireland', 'United States', 'Spain', etc.). Do NOT suggest singular cities, towns, states, or regions (e.g. NEVER suggest 'London', 'Berlin', 'Dublin', 'Bath', 'Amsterdam', 'Mumbai', 'California', or 'Texas'). Recommend 5–10 countries.
4. Set seniority_levels to match their experience (values: intern, entry, mid, senior, executive).
   Prefer slightly broader bands when it increases results (e.g. entry+mid for 2–4 years).
5. Prefer posted_within_hours of 168 (1 week) or 336 (2 weeks) for more results unless they are
   very senior and selective.
6. Only set min_salary / max_salary if the CV clearly signals an expectation; otherwise null.
7. Write a 2–3 sentence summary explaining the strategy.

Return ONLY valid JSON:
{{
  "roles": ["Title One", "Title Two"],
  "locations": ["Remote", "United Kingdom", "Germany"],
  "seniority_levels": ["entry", "mid"],
  "posted_within_hours": 168,
  "min_salary": null,
  "max_salary": null,
  "summary": "Brief explanation"
}}

--- CV ---
{cv[:8000]}

--- Cover letter ---
{cover[:3000] if cover else "(not provided)"}

--- Current location ---
{location or "(not provided)"}

--- Profile skills ---
{skills or "(none)"}

--- Profile summary ---
{summary or "(none)"}
"""

    result = await llm_generate(
        prompt,
        system=_SYSTEM,
        temperature=0.45,
        max_tokens=1536,
        api_key=resolve_gemini_api_key(profile),
        json_mode=True,
    )
    parsed = _extract_json_object(result)
    if parsed and parsed.get("roles"):
        return _normalize_criteria(parsed), ""

    if not result:
        return _default_criteria(), (
            "Could not generate suggestions. Ensure Ollama is running (or GEMINI_API_KEY "
            "is set if using cloud mode) and try again."
        )

    logger.warning("Search criteria suggester: unparseable response: %s", result[:500])
    return _default_criteria(), "Could not parse search criteria. Please try again."
