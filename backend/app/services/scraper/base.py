"""Job scraper registry and shared types."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class RawJob:
    external_id: str
    source: str
    title: str
    company: str
    url: str
    description: str = ""
    location: str = ""
    company_domain: str = ""
    posted_at: Optional[datetime] = None
    tags: list[str] = field(default_factory=list)
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_currency: str = ""
    salary_text: str = ""


RELOCATION_KEYWORDS = [
    "relocation",
    "relocate",
    "visa sponsorship",
    "visa sponsor",
    "work permit",
    "immigration support",
    "relocation package",
    "relocation assistance",
    "moving allowance",
    "global mobility",
    "international hire",
    "sponsor visa",
    "tier 2",
    "blue card",
    "work authorization support",
]

JUNIOR_KEYWORDS = [
    "graduate",
    "grad",
    "junior",
    "intern",
    "internship",
    "entry level",
    "entry-level",
    "early career",
    "new grad",
    "recent graduate",
    "trainee",
    "associate",
    "0-2 years",
    "0-1 years",
    "1-2 years",
]

# Only these experience levels are allowed by the search constraints.
ALLOWED_LEVELS = {"junior", "graduate", "intern"}

# Canonical seniority buckets the UI filter exposes.
SENIORITY_LEVELS = ("intern", "entry", "mid", "senior", "executive")

# Keyword sets per seniority bucket (matched as whole words). Ordered so the
# most specific/unambiguous buckets are checked first.
SENIORITY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("intern", ["intern", "internship", "interns", "placement student", "industrial placement"]),
    ("executive", [
        "ceo", "cto", "cfo", "coo", "cmo", "chief", "c-level", "cxo",
        "vp", "vice president", "head of", "director", "executive",
    ]),
    ("senior", [
        "senior", "sr", "sr.", "lead", "principal", "staff",
        "5+ years", "6+ years", "7+ years", "8+ years", "9+ years", "10+ years",
    ]),
    ("mid", ["mid-level", "mid level", "midlevel", "intermediate", "2+ years", "3+ years", "4+ years"]),
    ("entry", [
        "graduate", "grad", "new grad", "junior", "entry level", "entry-level",
        "early career", "trainee", "associate", "apprentice",
        "0-2 years", "0-1 years", "1-2 years",
    ]),
]

# Map a canonical seniority bucket to LinkedIn guest `f_E` experience codes.
# LinkedIn: 1 Internship, 2 Entry, 3 Associate, 4 Mid-Senior, 5 Director, 6 Executive.
LEVEL_TO_FE: dict[str, list[str]] = {
    "intern": ["1"],
    "entry": ["2", "3"],
    "mid": ["4"],
    "senior": ["4"],
    "executive": ["5", "6"],
}

# LinkedIn guest `f_SB2` salary buckets -> minimum USD threshold.
_SALARY_BUCKETS = [
    (40000, "1"), (60000, "2"), (80000, "3"), (100000, "4"), (120000, "5"),
    (140000, "6"), (160000, "7"), (180000, "8"), (200000, "9"),
]


def salary_to_fe_bucket(min_salary: Optional[int]) -> Optional[str]:
    """Largest LinkedIn salary bucket whose threshold is <= the desired minimum."""
    if not min_salary:
        return None
    chosen = None
    for threshold, code in _SALARY_BUCKETS:
        if min_salary >= threshold:
            chosen = code
    return chosen


_NON_ANNUAL = (
    "per hour", "/hr", " hourly", "an hour", "per day", " daily",
    "per month", "/mo", " monthly", "per week", " weekly",
)
_AMOUNT_RE = re.compile(
    r"(?P<sym>[£€$])?\s*(?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?P<suf>k|m)?",
    re.IGNORECASE,
)


def parse_salary(text: str) -> tuple[Optional[int], Optional[int], str, str]:
    """Best-effort annual-salary extraction. Returns (min, max, currency, label).

    Conservative on purpose: only counts amounts that carry a currency symbol/
    word, a thousands separator, or a k/m suffix (so "3+ years" or "2024" are
    ignored), and skips clearly hourly/monthly figures."""
    if not text:
        return (None, None, "", "")
    low = text.lower()
    if any(p in low for p in _NON_ANNUAL):
        return (None, None, "", "")

    currency = ""
    for sym in ("£", "€", "$"):
        if sym in text:
            currency = sym
            break
    if not currency:
        for word, sym in (("gbp", "£"), ("eur", "€"), ("usd", "$")):
            if re.search(r"\b" + word + r"\b", low):
                currency = sym
                break

    amounts: list[int] = []
    for m in _AMOUNT_RE.finditer(text):
        sym, num, suf = m.group("sym"), m.group("num"), (m.group("suf") or "").lower()
        if not (sym or suf or "," in num):
            continue  # bare number without a salary signal
        try:
            val = float(num.replace(",", ""))
        except ValueError:
            continue
        if suf == "k":
            val *= 1000
        elif suf == "m":
            val *= 1_000_000
        val = int(val)
        if 10000 <= val <= 1_000_000:
            amounts.append(val)

    if not amounts:
        return (None, None, currency, "")
    smin, smax = min(amounts), max(amounts)
    pfx = currency
    label = f"{pfx}{smin:,}" + (f" - {pfx}{smax:,}" if smax != smin else "")
    return (smin, smax, currency, label[:200])

# Signals that a remote role is open regardless of country. These are treated as
# satisfying the country filter so remote roles stay available even when they
# don't name one of the profile's target countries.
GLOBAL_LOCATION_SIGNALS = [
    "remote",
    "worldwide",
    "anywhere",
    "global",
    "international",
    "no location restriction",
    "remote (global)",
]

# Companies to always exclude from results.
EXCLUDED_COMPANIES = {
    "canonical",
}

# Phrases indicating a US-based role. Matched as whole words/phrases (see
# JobMatcher._is_us_location) so we don't trip on substrings like "business".
US_LOCATION_SIGNALS = [
    "united states",
    "united states of america",
    "usa",
    "u.s.a",
    "u.s.",
    "us only",
    "us-only",
    "us based",
    "us-based",
    "remote us",
    "remote - us",
    "us remote",
]

# Common aliases so a profile country like "uk" still matches "United Kingdom".
COUNTRY_ALIASES = {
    "uk": ["united kingdom", "england", "scotland", "wales", "britain", "gb"],
    "united kingdom": ["uk", "england", "scotland", "wales", "britain", "gb"],
    "usa": ["united states", "u.s.", "us", "america"],
    "us": ["united states", "u.s.", "usa", "america"],
    "united states": ["usa", "u.s.", "us", "america"],
    "uae": ["united arab emirates", "dubai", "abu dhabi"],
    "united arab emirates": ["uae", "dubai", "abu dhabi"],
    "germany": ["deutschland", "berlin", "munich"],
    "netherlands": ["holland", "amsterdam"],
    "ireland": ["dublin"],
    "canada": ["toronto", "vancouver", "montreal"],
    "australia": ["sydney", "melbourne"],
}
