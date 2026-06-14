"""Shared helpers for Google / LinkedIn OAuth redirects and URL resolution."""

from urllib.parse import urlencode

from fastapi.responses import RedirectResponse

from app.config import settings


def api_base_url() -> str:
    return settings.app_base_url.rstrip("/")


def frontend_callback_url() -> str:
    """Where users land after OAuth completes (SPA /auth/callback route)."""
    explicit = (settings.oauth_frontend_callback_url or "").strip()
    if explicit:
        return explicit.rstrip("/")
    return f"{api_base_url()}/auth/callback"


def oauth_redirect_uri(provider: str) -> str:
    """Backend callback registered with Google / LinkedIn developer consoles."""
    return f"{api_base_url()}/api/auth/{provider}/callback"


def oauth_error_redirect(message: str) -> RedirectResponse:
    params = urlencode({"error": message})
    return RedirectResponse(f"{frontend_callback_url()}?{params}")


def oauth_success_redirect(token: str) -> RedirectResponse:
    params = urlencode({"token": token})
    return RedirectResponse(f"{frontend_callback_url()}?{params}")


def oauth_provider_configured(provider: str) -> bool:
    if provider == "google":
        return bool(settings.google_client_id and settings.google_client_secret)
    if provider == "linkedin":
        return bool(settings.linkedin_client_id and settings.linkedin_client_secret)
    return False


def oauth_status() -> dict:
    return {
        "google": oauth_provider_configured("google"),
        "linkedin": oauth_provider_configured("linkedin"),
        "frontend_callback_url": frontend_callback_url(),
        "google_redirect_uri": oauth_redirect_uri("google"),
        "linkedin_redirect_uri": oauth_redirect_uri("linkedin"),
    }
