"""Job scraper registry and shared types."""

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
