"""Stripe billing wrapper: Checkout, Customer Portal, and webhook handling.

One USD recurring Price per tier; Stripe Adaptive Pricing (enabled in the
dashboard) charges each buyer in their local currency. Subscription state is
mirrored onto the User row via webhooks so plan resolution is local + fast.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.database import User

logger = logging.getLogger(__name__)

try:
    import stripe
except Exception:  # pragma: no cover - dependency installed in prod image
    stripe = None


_PRICE_BY_TIER = {
    "basic": lambda: settings.stripe_price_basic,
    "standard": lambda: settings.stripe_price_standard,
    "pro": lambda: settings.stripe_price_pro,
}


class BillingError(Exception):
    pass


def is_configured() -> bool:
    return bool(
        stripe
        and settings.stripe_secret_key
        and settings.stripe_price_basic
        and settings.stripe_price_standard
        and settings.stripe_price_pro
    )


def _client():
    if not is_configured():
        raise BillingError("Stripe is not configured")
    stripe.api_key = settings.stripe_secret_key
    return stripe


def price_for_tier(tier: str) -> str:
    getter = _PRICE_BY_TIER.get(tier)
    price = getter() if getter else ""
    if not price:
        raise BillingError(f"No Stripe price configured for tier '{tier}'")
    return price


def _ensure_customer(db: Session, user: User) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id
    client = _client()
    customer = client.Customer.create(email=user.email, metadata={"user_id": str(user.id)})
    user.stripe_customer_id = customer["id"]
    db.commit()
    return customer["id"]


def create_checkout_session(db: Session, user: User, tier: str) -> str:
    client = _client()
    price = price_for_tier(tier)
    customer_id = _ensure_customer(db, user)
    base = settings.app_base_url.rstrip("/")
    session = client.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price, "quantity": 1}],
        allow_promotion_codes=True,
        success_url=f"{base}/app/billing?status=success",
        cancel_url=f"{base}/app/billing?status=cancel",
        metadata={"user_id": str(user.id), "tier": tier},
        subscription_data={"metadata": {"user_id": str(user.id), "tier": tier}},
    )
    return session["url"]


def cancel_subscription(user: User) -> bool:
    """Best-effort immediate cancellation of the user's Stripe subscription
    (used during GDPR account deletion). Never raises."""
    if not is_configured() or not getattr(user, "stripe_subscription_id", ""):
        return False
    try:
        client = _client()
        try:
            client.Subscription.cancel(user.stripe_subscription_id)
        except AttributeError:  # older stripe-python
            client.Subscription.delete(user.stripe_subscription_id)
        return True
    except Exception as exc:  # pragma: no cover - external service
        logger.warning("Stripe cancellation failed for user %s: %s", user.id, exc)
        return False


def create_portal_session(db: Session, user: User) -> str:
    client = _client()
    if not user.stripe_customer_id:
        raise BillingError("No subscription to manage")
    base = settings.app_base_url.rstrip("/")
    session = client.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{base}/app/billing",
    )
    return session["url"]


def sync_user_subscription(db: Session, user: User) -> None:
    """Proactively sync the user's subscription from Stripe."""
    if not is_configured() or not user.stripe_customer_id:
        return
    try:
        client = _client()
        subs = client.Subscription.list(customer=user.stripe_customer_id, status="all", limit=1)
        if subs and subs.data:
            _apply_subscription(db, subs.data[0])
    except Exception as exc:
        logger.warning("Failed to sync subscription for user %s: %s", user.id, exc)

def _tier_from_price(price_id: Optional[str]) -> Optional[str]:
    if not price_id:
        return None
    for tier, getter in _PRICE_BY_TIER.items():
        if getter() and getter() == price_id:
            return tier
    return None


def _apply_subscription(db: Session, subscription: dict) -> None:
    """Mirror a Stripe subscription object onto the matching User."""
    customer_id = subscription.get("customer")
    user = (
        db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if customer_id
        else None
    )
    if not user:
        # Fall back to metadata.user_id (first event before customer is linked).
        uid = (subscription.get("metadata") or {}).get("user_id")
        if uid:
            user = db.query(User).filter(User.id == int(uid)).first()
    if not user:
        logger.warning("Stripe subscription for unknown customer %s", customer_id)
        return

    status = subscription.get("status", "")
    user.plan_status = status
    user.stripe_subscription_id = subscription.get("id", "") or user.stripe_subscription_id
    period_end = subscription.get("current_period_end")
    if period_end:
        user.current_period_end = datetime.utcfromtimestamp(period_end)

    # Resolve tier from the price on the first line item, else metadata.
    tier = None
    items = (subscription.get("items") or {}).get("data") or []
    if items:
        tier = _tier_from_price((items[0].get("price") or {}).get("id"))
    if not tier:
        tier = (subscription.get("metadata") or {}).get("tier")

    if status in ("active", "trialing") and tier:
        user.plan = tier
    elif status in ("canceled", "unpaid", "incomplete_expired"):
        user.plan = "expired"
    db.commit()


def handle_webhook(db: Session, payload: bytes, sig_header: str) -> str:
    client = _client()
    if not settings.stripe_webhook_secret:
        raise BillingError("Webhook secret not configured")
    try:
        event = client.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except Exception as exc:  # signature/parse failure
        raise BillingError(f"Invalid webhook: {exc}")

    etype = event["type"]
    obj = event["data"]["object"]

    if etype in ("customer.subscription.created", "customer.subscription.updated",
                 "customer.subscription.deleted"):
        _apply_subscription(db, obj)
    elif etype == "checkout.session.completed":
        sub_id = obj.get("subscription")
        if sub_id:
            sub = client.Subscription.retrieve(sub_id)
            _apply_subscription(db, sub)
    elif etype == "invoice.payment_failed":
        customer_id = obj.get("customer")
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            user.plan_status = "past_due"
            db.commit()

    return etype
