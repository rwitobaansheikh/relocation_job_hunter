import logging
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import create_access_token
from app.config import settings
from app.database import User, UserProfile, UserRole, get_db
from app.oauth_helpers import (
    oauth_error_redirect,
    oauth_provider_configured,
    oauth_redirect_uri,
    oauth_status,
    oauth_success_redirect,
)
from app.security import hash_password

logger = logging.getLogger(__name__)

oauth_router = APIRouter(prefix="/api/auth", tags=["oauth"])


def _ensure_user_profile(db: Session, user: User, email: str, name: str) -> None:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    if profile:
        return
    profile = UserProfile(
        user_id=user.id,
        full_name=name,
        email=email,
        daily_send_cap=settings.default_daily_send_cap,
        per_domain_cap=settings.default_per_domain_cap,
        automation_interval_hours=settings.default_automation_interval_hours,
        max_tailor_per_run=settings.default_max_tailor_per_run,
    )
    db.add(profile)
    db.commit()


def _get_or_create_oauth_user(db: Session, email: str, name: str, provider: str = "") -> User:
    user = db.query(User).filter(User.email == email).first()
    if user:
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account disabled")
        _ensure_user_profile(db, user, email, name)
        return user

    is_first = db.query(User).count() == 0
    random_password = secrets.token_urlsafe(32)
    user = User(
        email=email,
        password_hash=hash_password(random_password),
        role=UserRole.ADMIN.value if is_first else UserRole.USER.value,
        is_active=True,
        plan="trial",
        plan_status="trialing",
        trial_end=datetime.utcnow() + timedelta(days=settings.trial_days),
        oauth_provider=provider,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    profile = UserProfile(
        user_id=user.id,
        full_name=name,
        email=email,
        daily_send_cap=settings.default_daily_send_cap,
        per_domain_cap=settings.default_per_domain_cap,
        automation_interval_hours=settings.default_automation_interval_hours,
        max_tailor_per_run=settings.default_max_tailor_per_run,
    )
    db.add(profile)
    db.commit()

    return user


def _oauth_user_or_redirect(db: Session, email: str, name: str, provider: str = ""):
    try:
        return _get_or_create_oauth_user(db, email, name, provider)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Authentication failed"
        return oauth_error_redirect(detail)


@oauth_router.get("/oauth/status")
def get_oauth_status():
    return oauth_status()


# --- Google OAuth ---


@oauth_router.get("/google/url")
def get_google_oauth_url():
    if not oauth_provider_configured("google"):
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")

    state = secrets.token_urlsafe(16)
    redirect_uri = oauth_redirect_uri("google")
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
        "state": state,
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return {"url": url}


@oauth_router.get("/google/callback")
async def google_oauth_callback(
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if error:
        msg = error_description or error.replace("_", " ")
        return oauth_error_redirect(f"Google sign-in cancelled: {msg}")
    if not code:
        return oauth_error_redirect("Google sign-in failed: missing authorization code")
    if not oauth_provider_configured("google"):
        return oauth_error_redirect("Google sign-in is not configured on this server")

    redirect_uri = oauth_redirect_uri("google")

    async with httpx.AsyncClient(timeout=30.0) as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
        if token_resp.status_code != 200:
            logger.error("Google token error: %s", token_resp.text)
            return oauth_error_redirect("Google sign-in failed: could not verify authorization")

        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return oauth_error_redirect("Google sign-in failed: no access token returned")

        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            logger.error("Google userinfo error: %s", userinfo_resp.text)
            return oauth_error_redirect("Google sign-in failed: could not load profile")

        user_info = userinfo_resp.json()
        email = user_info.get("email")
        name = user_info.get("name", "User")

        if not email:
            return oauth_error_redirect("Google account has no email address")

        user = _oauth_user_or_redirect(db, email, name, "google")
        if not isinstance(user, User):
            return user

        jwt_token = create_access_token(user.id)
        return oauth_success_redirect(jwt_token)


# --- LinkedIn OAuth ---


@oauth_router.get("/linkedin/url")
def get_linkedin_oauth_url():
    if not oauth_provider_configured("linkedin"):
        raise HTTPException(status_code=503, detail="LinkedIn sign-in is not configured")

    state = secrets.token_urlsafe(16)
    redirect_uri = oauth_redirect_uri("linkedin")
    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
        "state": state,
    }
    url = f"https://www.linkedin.com/oauth/v2/authorization?{urlencode(params)}"
    return {"url": url}


@oauth_router.get("/linkedin/callback")
async def linkedin_oauth_callback(
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if error:
        msg = error_description or error.replace("_", " ")
        return oauth_error_redirect(f"LinkedIn sign-in cancelled: {msg}")
    if not code:
        return oauth_error_redirect("LinkedIn sign-in failed: missing authorization code")
    if not oauth_provider_configured("linkedin"):
        return oauth_error_redirect("LinkedIn sign-in is not configured on this server")

    redirect_uri = oauth_redirect_uri("linkedin")

    async with httpx.AsyncClient(timeout=30.0) as client:
        token_resp = await client.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.linkedin_client_id,
                "client_secret": settings.linkedin_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_resp.status_code != 200:
            logger.error("LinkedIn token error: %s", token_resp.text)
            return oauth_error_redirect("LinkedIn sign-in failed: could not verify authorization")

        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return oauth_error_redirect("LinkedIn sign-in failed: no access token returned")

        userinfo_resp = await client.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if userinfo_resp.status_code != 200:
            logger.error("LinkedIn userinfo error: %s", userinfo_resp.text)
            return oauth_error_redirect("LinkedIn sign-in failed: could not load profile")

        user_info = userinfo_resp.json()
        email = user_info.get("email")
        name = (
            user_info.get("name")
            or f"{user_info.get('given_name', '')} {user_info.get('family_name', '')}".strip()
            or "User"
        )

        if not email:
            return oauth_error_redirect("LinkedIn account has no email address")

        user = _oauth_user_or_redirect(db, email, name, "linkedin")
        if not isinstance(user, User):
            return user

        jwt_token = create_access_token(user.id)
        return oauth_success_redirect(jwt_token)
