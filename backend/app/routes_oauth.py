import logging
from datetime import datetime, timedelta
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import create_access_token
from app.config import settings
from app.database import User, UserProfile, UserRole, get_db
from app.security import hash_password

logger = logging.getLogger(__name__)

oauth_router = APIRouter(prefix="/api/auth", tags=["oauth"])


def _get_or_create_oauth_user(db: Session, email: str, name: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user:
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account disabled")
        return user

    # Create new user
    is_first = db.query(User).count() == 0
    # Use a strong random password for OAuth users since they don't log in with passwords
    random_password = secrets.token_urlsafe(32)
    user = User(
        email=email,
        password_hash=hash_password(random_password),
        role=UserRole.ADMIN.value if is_first else UserRole.USER.value,
        is_active=True,
        plan="trial",
        plan_status="trialing",
        trial_end=datetime.utcnow() + timedelta(days=settings.trial_days),
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


# --- Google OAuth ---

@oauth_router.get("/google/url")
def get_google_oauth_url():
    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
        
    # The callback URL must match exactly what is registered in Google Cloud Console
    redirect_uri = f"{settings.app_base_url.rstrip('/')}/api/auth/google/callback"
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account"
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return {"url": url}


@oauth_router.get("/google/callback")
async def google_oauth_callback(code: str, db: Session = Depends(get_db)):
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")
        
    redirect_uri = f"{settings.app_base_url.rstrip('/')}/api/auth/google/callback"
    
    async with httpx.AsyncClient() as client:
        # 1. Exchange code for access token
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            }
        )
        if token_resp.status_code != 200:
            logger.error(f"Google token error: {token_resp.text}")
            raise HTTPException(status_code=400, detail="Failed to exchange token with Google")
            
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        
        # 2. Get user info
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if userinfo_resp.status_code != 200:
            logger.error(f"Google userinfo error: {userinfo_resp.text}")
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")
            
        user_info = userinfo_resp.json()
        email = user_info.get("email")
        name = user_info.get("name", "User")
        
        if not email:
            raise HTTPException(status_code=400, detail="Google account has no email")
            
        # 3. Create or get user
        user = _get_or_create_oauth_user(db, email, name)
        
        # 4. Generate JWT
        jwt_token = create_access_token(user.id)
        
        # 5. Redirect to frontend with token
        return RedirectResponse(f"{settings.oauth_frontend_callback_url}?token={jwt_token}")


# --- LinkedIn OAuth ---

@oauth_router.get("/linkedin/url")
def get_linkedin_oauth_url():
    if not settings.linkedin_client_id:
        raise HTTPException(status_code=500, detail="LinkedIn OAuth not configured")
        
    redirect_uri = f"{settings.app_base_url.rstrip('/')}/api/auth/linkedin/callback"
    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid profile email",
    }
    url = f"https://www.linkedin.com/oauth/v2/authorization?{urlencode(params)}"
    return {"url": url}


@oauth_router.get("/linkedin/callback")
async def linkedin_oauth_callback(code: str, db: Session = Depends(get_db)):
    if not settings.linkedin_client_id or not settings.linkedin_client_secret:
        raise HTTPException(status_code=500, detail="LinkedIn OAuth not configured")
        
    redirect_uri = f"{settings.app_base_url.rstrip('/')}/api/auth/linkedin/callback"
    
    async with httpx.AsyncClient() as client:
        # 1. Exchange code for access token
        token_resp = await client.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.linkedin_client_id,
                "client_secret": settings.linkedin_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if token_resp.status_code != 200:
            logger.error(f"LinkedIn token error: {token_resp.text}")
            raise HTTPException(status_code=400, detail="Failed to exchange token with LinkedIn")
            
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        
        # 2. Get user info using OpenID endpoint
        userinfo_resp = await client.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if userinfo_resp.status_code != 200:
            logger.error(f"LinkedIn userinfo error: {userinfo_resp.text}")
            raise HTTPException(status_code=400, detail="Failed to get user info from LinkedIn")
            
        user_info = userinfo_resp.json()
        email = user_info.get("email")
        name = user_info.get("name") or f"{user_info.get('given_name', '')} {user_info.get('family_name', '')}".strip() or "User"
        
        if not email:
            raise HTTPException(status_code=400, detail="LinkedIn account has no email")
            
        # 3. Create or get user
        user = _get_or_create_oauth_user(db, email, name)
        
        # 4. Generate JWT
        jwt_token = create_access_token(user.id)
        
        # 5. Redirect to frontend with token
        return RedirectResponse(f"{settings.oauth_frontend_callback_url}?token={jwt_token}")