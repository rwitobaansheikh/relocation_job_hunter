"""Stripe billing wrapper: Checkout, Customer Portal, and webhook handling.

One USD recurring Price per tier; Stripe Adaptive Pricing (enabled in the
dashboard) charges each buyer in their local currency. Subscription state is
mirrored onto the User row via webhooks so plan resolution is local + fast.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

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


def create_checkout_session(
    db: Session, user: User, tier: str, *, with_trial: bool = False
) -> str:
    client = _client()
    price = price_for_tier(tier)
    customer_id = _ensure_customer(db, user)
    base = settings.app_base_url.rstrip("/")

    subscription_data: dict = {"metadata": {"user_id": str(user.id), "tier": tier}}
    if with_trial:
        subscription_data["trial_period_days"] = settings.trial_days

    session = client.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price, "quantity": 1}],
        allow_promotion_codes=True,
        payment_method_collection="always",
        success_url=f"{base}/app/billing?status=success",
        cancel_url=f"{base}/app/billing?status=cancel",
        metadata={"user_id": str(user.id), "tier": tier, "trial": str(with_trial).lower()},
        subscription_data=subscription_data,
    )
    return session["url"]


def create_trial_checkout_session(db: Session, user: User) -> str:
    """Start a Stripe subscription with a free trial; card is charged when trial ends."""
    tier = settings.trial_default_tier or "basic"
    return create_checkout_session(db, user, tier, with_trial=True)


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


def _stripe_id(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("id") or ""
    return getattr(value, "id", "") or ""


def _price_id_from_item(item: dict) -> Optional[str]:
    price = item.get("price")
    if isinstance(price, str):
        return price or None
    if isinstance(price, dict):
        return price.get("id") or None
    return _stripe_id(price) or None


def _tier_from_price(price_id: Optional[str]) -> Optional[str]:
    if not price_id:
        return None
    for tier, getter in _PRICE_BY_TIER.items():
        configured = getter()
        if configured and configured == price_id:
            return tier
    return None


def _resolve_user(
    db: Session,
    *,
    customer_id: str | None = None,
    user_id: str | None = None,
) -> User | None:
    user = None
    if user_id:
        try:
            user = db.query(User).filter(User.id == int(user_id)).first()
        except (TypeError, ValueError):
            user = None
    if not user and customer_id:
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
    return user


def _schedule_system_email(to: str, subject: str, text: str, html: str | None) -> None:
    from app.services.system_email import send_system_email

    async def _send() -> None:
        ok, err = await send_system_email(to, subject, text, html)
        if not ok:
            logger.warning("Subscription email failed to %s: %s", to, err)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send())
    except RuntimeError:
        asyncio.run(_send())


def _maybe_send_subscription_email(
    db: Session,
    user: User,
    *,
    tier: str,
    subscription_id: str,
    status: str,
    payment_amount_cents: int | None = None,
    payment_currency: str = "usd",
) -> None:
    from app.services.subscription_notifications import (
        send_subscription_confirmation_email,
        should_send_subscription_email,
        subscription_email_key,
    )

    if status not in ("active", "trialing") or not tier or not subscription_id:
        return

    paid = bool(payment_amount_cents and payment_amount_cents > 0)
    email_key = subscription_email_key(subscription_id, tier, paid=paid)
    if not should_send_subscription_email(user, tier, email_key):
        return

    to, subject, text, html = send_subscription_confirmation_email(
        user,
        tier,
        payment_amount_cents=payment_amount_cents,
        payment_currency=payment_currency,
        trialing=status == "trialing" and not paid,
    )
    user.subscription_email_key = email_key
    db.commit()
    _schedule_system_email(to, subject, text, html)
    logger.info("Subscription confirmation email queued for user %s tier=%s", user.id, tier)


def _apply_subscription(
    db: Session,
    subscription: dict,
    *,
    tier_hint: str | None = None,
    notify: bool = False,
    payment_amount_cents: int | None = None,
    payment_currency: str = "usd",
) -> User | None:
    """Mirror a Stripe subscription object onto the matching User."""
    customer_id = _stripe_id(subscription.get("customer"))
    metadata = subscription.get("metadata") or {}
    user = _resolve_user(
        db,
        customer_id=customer_id or None,
        user_id=metadata.get("user_id"),
    )
    if not user:
        logger.warning("Stripe subscription for unknown customer %s", customer_id)
        return None

    if customer_id:
        user.stripe_customer_id = customer_id

    status = subscription.get("status", "")
    subscription_id = subscription.get("id", "") or user.stripe_subscription_id
    user.plan_status = status
    user.stripe_subscription_id = subscription_id

    period_end = subscription.get("current_period_end")
    if period_end:
        user.current_period_end = datetime.utcfromtimestamp(period_end)

    tier = tier_hint
    items = (subscription.get("items") or {}).get("data") or []
    if not tier and items:
        tier = _tier_from_price(_price_id_from_item(items[0]))
    if not tier:
        tier = metadata.get("tier")

    if status in ("active", "trialing") and tier:
        user.plan = tier
    elif status in ("canceled", "unpaid", "incomplete_expired"):
        user.plan = "expired"

    db.commit()
    db.refresh(user)

    if notify:
        _maybe_send_subscription_email(
            db,
            user,
            tier=tier or "",
            subscription_id=subscription_id or "",
            status=status,
            payment_amount_cents=payment_amount_cents,
            payment_currency=payment_currency,
        )

    return user


def _apply_checkout_session(db: Session, session: dict) -> None:
    """Apply plan changes immediately after Stripe Checkout completes."""
    metadata = session.get("metadata") or {}
    tier_hint = metadata.get("tier")
    customer_id = _stripe_id(session.get("customer"))
    user_id = metadata.get("user_id")

    user = _resolve_user(db, customer_id=customer_id or None, user_id=user_id)
    if not user:
        logger.warning("Checkout session for unknown user (customer=%s)", customer_id)
        return

    if customer_id:
        user.stripe_customer_id = customer_id
        db.commit()

    sub_id = _stripe_id(session.get("subscription"))
    if not sub_id:
        return

    client = _client()
    sub = client.Subscription.retrieve(sub_id, expand=["items.data.price"])
    payment_status = session.get("payment_status") or ""
    amount = session.get("amount_total")
    currency = session.get("currency") or "usd"
    paid_cents = amount if payment_status == "paid" and amount else None

    _apply_subscription(
        db,
        sub,
        tier_hint=tier_hint,
        notify=True,
        payment_amount_cents=paid_cents,
        payment_currency=currency,
    )


def sync_user_subscription(db: Session, user: User) -> bool:
    """Proactively sync the user's subscription from Stripe. Returns True if updated."""
    if not is_configured() or not user.stripe_customer_id:
        return False
    try:
        client = _client()
        for status in ("active", "trialing", "past_due"):
            subs = client.Subscription.list(
                customer=user.stripe_customer_id,
                status=status,
                limit=1,
                expand=["data.items.data.price"],
            )
            if subs and subs.data:
                _apply_subscription(db, subs.data[0])
                db.refresh(user)
                return True

        subs = client.Subscription.list(
            customer=user.stripe_customer_id,
            status="all",
            limit=5,
            expand=["data.items.data.price"],
        )
        for sub in subs.data or []:
            if sub.get("status") in ("active", "trialing"):
                _apply_subscription(db, sub)
                db.refresh(user)
                return True
    except Exception as exc:
        logger.warning("Failed to sync subscription for user %s: %s", user.id, exc)
    return False


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

    if etype in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        _apply_subscription(db, obj, notify=etype == "customer.subscription.created")
    elif etype == "checkout.session.completed":
        _apply_checkout_session(db, obj)
    elif etype == "invoice.payment_failed":
        customer_id = _stripe_id(obj.get("customer"))
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user:
            user.plan_status = "past_due"
            db.commit()
    elif etype == "invoice.payment_succeeded":
        sub_id = _stripe_id(obj.get("subscription"))
        amount_paid = obj.get("amount_paid") or 0
        currency = obj.get("currency") or "usd"
        billing_reason = obj.get("billing_reason") or ""

        if sub_id:
            sub = client.Subscription.retrieve(sub_id, expand=["items.data.price"])
            notify = amount_paid > 0 and billing_reason in (
                "subscription_create",
                "subscription_update",
                "subscription_cycle",
            )
            _apply_subscription(
                db,
                sub,
                notify=notify,
                payment_amount_cents=amount_paid if amount_paid > 0 else None,
                payment_currency=currency,
            )
        else:
            customer_id = _stripe_id(obj.get("customer"))
            user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
            if user:
                sync_user_subscription(db, user)
    elif etype == "customer.subscription.trial_will_end":
        _apply_subscription(db, obj)
        customer_id = _stripe_id(obj.get("customer"))
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
        if user and not user.trial_reminder_sent:
            from app.services.trial_notifications import send_trial_ending_email
            from app.services.system_email import send_system_email

            to, subject, text, html = send_trial_ending_email(user)
            _schedule_system_email(to, subject, text, html)
            user.trial_reminder_sent = True
            db.commit()

    return etype
