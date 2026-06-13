"""Build LinkedIn job-search query parameters (ported from n8n workflow).

Maps the app's search UI fields to LinkedIn guest-search params:
  - roles            -> keywords
  - locations        -> location (+ optional f_WT work-type codes)
  - seniority_levels -> f_E experience codes
  - posted_within    -> f_TPR=r{seconds}
  - min_salary       -> f_SB2 salary bucket
  - work_types       -> f_WT (remote / hybrid / on-site)
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlencode

from app.services.scraper.base import LEVEL_TO_FE

PUBLIC_SEARCH_URL = "https://www.linkedin.com/jobs/search/"
GUEST_SEARCH_URL = (
    "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
)

# LinkedIn f_WT: 1 = On-Site, 2 = Remote, 3 = Hybrid
WORK_TYPE_TO_CODE: dict[str, str] = {
    "remote": "2",
    "hybrid": "3",
    "onsite": "1",
    "on_site": "1",
    "on-site": "1",
}

# Location tokens that are work-type filters, not geographic places.
_WORK_TYPE_LOCATION_TOKENS = frozenset(WORK_TYPE_TO_CODE.keys()) | {"on site"}


def experience_codes_for_levels(seniority_levels: list[str]) -> Optional[str]:
    """Map UI seniority buckets to LinkedIn f_E codes."""
    codes: list[str] = []
    for level in seniority_levels:
        codes.extend(LEVEL_TO_FE.get(level, []))
    if not codes:
        return None
    return ",".join(sorted(set(codes), key=int))


def split_locations(locations: list[str]) -> tuple[list[str], list[str]]:
    """Split mixed location input into geographic places and f_WT codes."""
    geo: list[str] = []
    work_codes: list[str] = []
    for raw in locations:
        token = (raw or "").strip()
        if not token:
            continue
        key = token.lower()
        if key in _WORK_TYPE_LOCATION_TOKENS:
            code = WORK_TYPE_TO_CODE.get(key.replace(" ", "_"), WORK_TYPE_TO_CODE.get(key))
            if not code and key == "on site":
                code = "1"
            if code:
                work_codes.append(code)
        else:
            geo.append(token)
    return geo, sorted(set(work_codes), key=int)


def resolve_work_type_codes(
    work_types: list[str] | None,
    locations: list[str] | None,
) -> list[str]:
    """Combine explicit work-type UI picks with tokens parsed from locations."""
    codes: list[str] = []
    for wt in work_types or []:
        code = WORK_TYPE_TO_CODE.get((wt or "").strip().lower().replace("-", "_"))
        if code:
            codes.append(code)
    _, from_locations = split_locations(locations or [])
    codes.extend(from_locations)
    return sorted(set(codes), key=int)


def build_linkedin_search_params(
    *,
    keywords: str = "",
    location: str = "",
    age_hours: int = 48,
    experience_codes: Optional[str] = None,
    work_type_codes: Optional[list[str]] = None,
    salary_bucket: Optional[str] = None,
    start: int = 0,
) -> dict[str, str]:
    """Build query params for LinkedIn guest search / public search URLs."""
    seconds = max(int(age_hours), 1) * 3600
    params: dict[str, str] = {
        "f_TPR": f"r{seconds}",
        "start": str(start),
    }

    if experience_codes:
        params["f_E"] = experience_codes
    if keywords.strip():
        params["keywords"] = keywords.strip()
    if location.strip():
        params["location"] = location.strip()
    if work_type_codes:
        params["f_WT"] = ",".join(work_type_codes)
    if salary_bucket:
        params["f_SB2"] = salary_bucket

    return params


def build_linkedin_search_url(params: dict[str, str]) -> str:
    return f"{PUBLIC_SEARCH_URL}?{urlencode(params)}"
