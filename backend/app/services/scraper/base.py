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
