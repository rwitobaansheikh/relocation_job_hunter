"""Billing routes: plan status, Stripe Checkout, Customer Portal, and webhook."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.database import AutomationLoop, User, UserProfile, get_db
from app.schemas import (
    BillingLimits,
    BillingResponse,
    BillingTier,
    BillingUsage,
    CheckoutRequest,
    CheckoutResponse,
)
from app.services import billing
from app.services.plans import TIERS, current_plan, effective_limits, localized_price
from app.services.usage import get_usage

logger = logging.getLogger(__name__)

billing_router = APIRouter(prefix="/api/billing", tags=["billing"])
webhook_router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _tiers_for_country(country: str | None) -> list[BillingTier]:
    out: list[BillingTier] = []
    for t in TIERS:
        price = localized_price(t["price_usd"], country)
        out.append(
            BillingTier(
                id=t["id"],
                name=t["name"],
                price_usd=t["price_usd"],
                price_display=f"{price['display']}/mo",
                currency=price["currency"],
                is_estimate=price["is_estimate"],
                features=t["features"],
            )
        )
    return out


@billing_router.get("", response_model=BillingResponse)
def get_billing(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    country = request.headers.get("CF-IPCountry") or request.headers.get("cf-ipcountry")
    
    # Proactively sync subscription status if the user has a customer ID
    # This ensures immediate updates after checkout returns to the app
    billing.sync_user_subscription(db, user)
    db.refresh(user)
    limits = effective_limits(user)

    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
    manual_today = get_usage(db, profile.id, "manual") if profile else 0
    tailor_today = get_usage(db, profile.id, "tailor") if profile else 0
    llm_today = get_usage(db, profile.id, "llm") if profile else 0
    loops_active = (
        db.query(AutomationLoop)
        .filter(
            AutomationLoop.user_profile_id == profile.id,
            AutomationLoop.enabled.is_(True),
        )
        .count()
        if profile
        else 0
    )

    days_left = 0
    if user.trial_end and user.trial_end > datetime.utcnow():
        days_left = (user.trial_end - datetime.utcnow()).days + 1

    return BillingResponse(
        plan=current_plan(user),
        plan_status=user.plan_status or "",
        trial_end=user.trial_end,
        trial_days_left=days_left,
        trial_days=settings.trial_days,
        current_period_end=user.current_period_end,
        unlimited_access=bool(user.unlimited_access),
        is_admin=user.role == "admin",
        stripe_configured=billing.is_configured(),
        has_stripe_subscription=bool(user.stripe_subscription_id),
        limits=BillingLimits(
            max_loops=limits.max_loops,
            auto_per_loop_per_day=limits.auto_per_loop_per_day,
            manual_per_day=limits.manual_per_day,
            tailor_per_day=limits.tailor_per_day,
            llm_per_day=limits.llm_per_day,
        ),
        usage=BillingUsage(
            manual_today=manual_today, 
            loops_active=loops_active,
            tailor_today=tailor_today,
            llm_today=llm_today
        ),
        tiers=_tiers_for_country(country),
    )


@billing_router.post("/trial-checkout", response_model=CheckoutResponse)
def trial_checkout(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a 3-day free trial on Basic; card is charged automatically when trial ends."""
    if user.stripe_subscription_id and user.plan_status in ("active", "trialing"):
        raise HTTPException(status_code=400, detail="You already have an active subscription")
    try:
        url = billing.create_trial_checkout_session(db, user)
    except billing.BillingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return CheckoutResponse(url=url)


@billing_router.post("/checkout", response_model=CheckoutResponse)
def checkout(
    data: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.tier not in {t["id"] for t in TIERS}:
        raise HTTPException(status_code=400, detail="Unknown plan")
    try:
        url = billing.create_checkout_session(db, user, data.tier)
    except billing.BillingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return CheckoutResponse(url=url)


@billing_router.post("/portal", response_model=CheckoutResponse)
def portal(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        url = billing.create_portal_session(db, user)
    except billing.BillingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return CheckoutResponse(url=url)


@webhook_router.post("/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        etype = billing.handle_webhook(db, payload, sig)
    except billing.BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"received": True, "type": etype}
