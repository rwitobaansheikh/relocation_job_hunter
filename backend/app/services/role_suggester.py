"""Suggest job roles — delegates to the full search-criteria suggester."""

from app.database import UserProfile
from app.services.search_criteria_suggester import suggest_search_criteria


async def suggest_roles(profile: UserProfile) -> tuple[list[str], str]:
    """Return (roles, message). Kept for backward compatibility."""
    criteria, message = await suggest_search_criteria(profile)
    return criteria.get("roles", []), message
