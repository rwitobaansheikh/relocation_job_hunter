"""Stripe billing wrapper: Checkout, Customer Portal, and webhook handling.

One USD recurring Price per tier; Stripe Adaptive Pricing (enabled in the
dashboard) charges each buyer in their local currency. Subscription state is
mirrored onto the User row via webhooks so plan resolution is local + fast.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import User
from app.services.plans import PAID_PLANS, current_plan

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


@dataclass
class ApplyResult:
    """Outcome of mirroring a Stripe object onto a User row. ``applied`` is True
    only when a plan/status change was actually written, so the webhook can
    report real success/failure to Stripe instead of always returning 200."""

    applied: bool
    reason: str = ""
    user_id: int | None = None


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
        success_url=f"{base}/app/billing?status=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base}/app/billing?status=cancel",
        metadata={"user_id": str(user.id), "tier": tier, "trial": str(with_trial).lower()},
        subscription_data=subscription_data,
        client_reference_id=str(user.id),
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
    price_id = _stripe_id(price) or None
    if price_id:
        return price_id
    plan = item.get("plan")
    if isinstance(plan, str):
        return plan or None
    if isinstance(plan, dict):
        return plan.get("id") or None
    return None


def _subscription_items(subscription: Any) -> list:
    items = subscription.get("items") if hasattr(subscription, "get") else None
    if items is None:
        return []
    if hasattr(items, "data"):
        return list(items.data or [])
    if isinstance(items, dict):
        return items.get("data") or []
    return []


def _tier_from_line_item(item: dict) -> Optional[str]:
    tier = _tier_from_price(_price_id_from_item(item))
    if tier:
        return tier
    price = item.get("price")
    if isinstance(price, dict):
        for hint in (price.get("nickname") or "", price.get("lookup_key") or ""):
            hint_lower = hint.lower()
            for candidate in PAID_PLANS:
                if candidate in hint_lower:
                    return candidate
    return None


def _tier_from_price(price_id: Optional[str]) -> Optional[str]:
    if not price_id:
        return None
    for tier, getter in _PRICE_BY_TIER.items():
        configured = getter()
        if configured and configured == price_id:
            return tier
    return None


def _stripe_customer_ids_for_user(user: User) -> list[str]:
    """All Stripe customer IDs that may belong to this user (DB + email lookup)."""
    seen: set[str] = set()
    out: list[str] = []
    if user.stripe_customer_id:
        seen.add(user.stripe_customer_id)
        out.append(user.stripe_customer_id)
    if not is_configured():
        return out
    try:
        client = _client()
        for cust in client.Customer.list(email=user.email, limit=10).data or []:
            cid = _stripe_id(cust)
            if not cid or cid in seen:
                continue
            meta_uid = (cust.get("metadata") or {}).get("user_id")
            if meta_uid and str(meta_uid) != str(user.id):
                continue
            seen.add(cid)
            out.append(cid)
    except Exception as exc:
        logger.warning("Stripe customer list failed for user %s: %s", user.id, exc)
    return out


def _resolve_user(
    db: Session,
    *,
    customer_id: str | None = None,
    user_id: str | None = None,
    client_reference_id: str | None = None,
    customer_email: str | None = None,
) -> User | None:
    user = None
    for raw_id in (user_id, client_reference_id):
        if user or not raw_id:
            continue
        try:
            user = db.query(User).filter(User.id == int(raw_id)).first()
        except (TypeError, ValueError):
            user = None
    if not user and customer_id:
        user = db.query(User).filter(User.stripe_customer_id == customer_id).first()

    # Last-resort fallback: match by the Stripe customer's email. This recovers
    # subscriptions created outside the app's own Checkout (Stripe Payment Links,
    # Pricing Tables, Buy Buttons, or subs created from the dashboard) which carry
    # no user_id metadata and whose customer isn't yet linked to a User row.
    if not user and customer_id and not customer_email and is_configured():
        try:
            cust = _client().Customer.retrieve(customer_id)
            customer_email = (cust.get("email") if hasattr(cust, "get") else None) or None
        except Exception as exc:  # pragma: no cover - external service
            logger.warning(
                "Could not retrieve customer %s for email fallback: %s", customer_id, exc
            )
    if not user and customer_email:
        email = customer_email.strip()
        user = db.query(User).filter(func.lower(User.email) == email.lower()).first()
        if user and customer_id and not user.stripe_customer_id:
            # Link the customer so subsequent lookups are direct.
            user.stripe_customer_id = customer_id
            db.commit()
            logger.info(
                "Linked Stripe customer %s to user %s via email fallback",
                customer_id,
                user.id,
            )
    return user


def _session_user_id(session: dict) -> str | None:
    metadata = session.get("metadata") or {}
    uid = metadata.get("user_id") or session.get("client_reference_id")
    return str(uid) if uid else None


def _checkout_is_complete(session: dict) -> bool:
    return session.get("payment_status") in ("paid", "no_payment_required")


def _session_belongs_to_user(session: dict, user: User) -> bool:
    session_uid = _session_user_id(session)
    if session_uid and session_uid != str(user.id):
        return False
    customer_id = _stripe_id(session.get("customer"))
    if (
        customer_id
        and user.stripe_customer_id
        and customer_id != user.stripe_customer_id
        and session_uid != str(user.id)
    ):
        return False
    return True


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
    if hasattr(user, "subscription_email_key"):
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
) -> ApplyResult:
    """Mirror a Stripe subscription object onto the matching User."""
    customer_id = _stripe_id(subscription.get("customer"))
    metadata = subscription.get("metadata") or {}
    user = _resolve_user(
        db,
        customer_id=customer_id or None,
        user_id=metadata.get("user_id"),
    )
    if not user:
        reason = f"user_not_found (customer={customer_id} user_id={metadata.get('user_id')})"
        logger.warning("Stripe subscription not applied: %s", reason)
        return ApplyResult(False, reason)

    if customer_id:
        user.stripe_customer_id = customer_id

    status = subscription.get("status", "")
    subscription_id = subscription.get("id", "") or user.stripe_subscription_id
    prev_plan, prev_status = user.plan, user.plan_status
    user.plan_status = status
    user.stripe_subscription_id = subscription_id

    period_end = subscription.get("current_period_end")
    items = _subscription_items(subscription)
    if not period_end and items:
        # Stripe API 2025-03-31+ moved current_period_end onto subscription items.
        first = items[0]
        period_end = first.get("current_period_end") if hasattr(first, "get") else None
    if period_end:
        user.current_period_end = datetime.utcfromtimestamp(period_end)

    tier = tier_hint
    if not tier and items:
        tier = _tier_from_line_item(items[0])
    if not tier:
        tier = metadata.get("tier")

    # Always clear the internal trial when a Stripe subscription is active so the
    # user cannot be stuck on "trial" even if tier resolution fails.
    if status in ("active", "trialing", "incomplete", "past_due"):
        user.trial_end = None

    applied = False
    reason = ""
    if status in ("active", "trialing", "incomplete") and tier:
        user.plan = tier
        applied = True
    elif status in ("canceled", "unpaid", "incomplete_expired"):
        user.plan = "expired"
        applied = True
    elif status in ("active", "trialing") and not tier:
        reason = (
            f"tier_unresolved (sub={subscription_id} status={status}); "
            "check STRIPE_PRICE_* match the live price IDs and subscription metadata"
        )
        logger.warning("Stripe subscription %s for user %s: %s", subscription_id, user.id, reason)
    else:
        # User resolved and plan_status persisted (e.g. past_due, paused); this is
        # a legitimate state sync, not a failure.
        applied = True
        reason = f"status_synced ({status})"

    db.commit()
    db.refresh(user)
    if applied:
        logger.info(
            "Applied subscription for user %s: plan %s->%s status %s->%s (sub=%s)",
            user.id, prev_plan, user.plan, prev_status, status, subscription_id,
        )

    if notify:
        try:
            _maybe_send_subscription_email(
                db,
                user,
                tier=tier or "",
                subscription_id=subscription_id or "",
                status=status,
                payment_amount_cents=payment_amount_cents,
                payment_currency=payment_currency,
            )
        except Exception as e:
            logger.warning("Failed to send subscription email for user %s: %s", user.id, e)

    return ApplyResult(applied, reason, user.id)


def _apply_checkout_session(
    db: Session, session: dict, *, user: User | None = None
) -> ApplyResult:
    """Apply plan changes immediately after Stripe Checkout completes.

    Structured in two phases so that a Stripe API failure in Phase 2 can never
    prevent the user's plan from being updated:

    Phase 1 (no Stripe API calls, always committed if checkout is complete):
      - Set stripe_customer_id, stripe_subscription_id
      - Clear trial_end, set plan_status, set plan from session metadata
      - db.commit()

    Phase 2 (best-effort, Stripe API calls):
      - Retrieve full subscription and call _apply_subscription for email +
        subscription-level metadata sync.
    """
    metadata = session.get("metadata") or {}
    tier_hint = metadata.get("tier")
    customer_id = _stripe_id(session.get("customer"))
    user_id = metadata.get("user_id") or session.get("client_reference_id")
    details = session.get("customer_details") or {}
    customer_email = session.get("customer_email") or (
        details.get("email") if hasattr(details, "get") else None
    )
    payment_status = session.get("payment_status") or ""
    sub_id = _stripe_id(session.get("subscription"))

    logger.info(
        "_apply_checkout_session START: session=%s payment_status=%s tier=%s "
        "user_id=%s customer=%s sub=%s",
        session.get("id"),
        payment_status,
        tier_hint,
        user_id,
        customer_id,
        sub_id,
    )

    resolved = user or _resolve_user(
        db,
        customer_id=customer_id or None,
        user_id=user_id,
        client_reference_id=session.get("client_reference_id"),
        customer_email=customer_email,
    )
    if not resolved:
        reason = (
            f"user_not_found (customer={customer_id} user_id={user_id} "
            f"email={customer_email})"
        )
        logger.warning("Checkout session not applied: %s", reason)
        return ApplyResult(False, reason)
    user = resolved

    checkout_complete = _checkout_is_complete(session)
    if not checkout_complete:
        reason = f"checkout_incomplete (payment_status={payment_status})"
        logger.info("_apply_checkout_session: %s for user %s", reason, user.id)
        return ApplyResult(False, reason)

    # ── Phase 1: commit facts derived purely from the session dict ────────────
    # This must not call _client() so that a Stripe misconfiguration cannot
    # block a user from seeing their paid plan.
    if customer_id:
        user.stripe_customer_id = customer_id
    if sub_id:
        user.stripe_subscription_id = sub_id
    user.trial_end = None
    if payment_status == "no_payment_required":
        user.plan_status = "trialing"
    elif payment_status == "paid":
        user.plan_status = "active"

    # Resolve tier: prefer session metadata, fall back to app default so the
    # plan column is always a paid value after a completed checkout.
    resolved_tier = tier_hint if tier_hint in PAID_PLANS else (settings.trial_default_tier or "basic")
    prev_plan = user.plan
    user.plan = resolved_tier

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(
            "_apply_checkout_session Phase 1 commit failed for user %s: %s",
            user.id,
            exc,
        )
        return ApplyResult(False, f"db_commit_failed: {exc}", user.id)

    logger.info(
        "_apply_checkout_session Phase 1 committed: plan %s->%s status=%s "
        "sub=%s for user %s",
        prev_plan,
        resolved_tier,
        user.plan_status,
        sub_id,
        user.id,
    )

    if not sub_id:
        return ApplyResult(True, "", user.id)

    # ── Phase 2: retrieve full subscription (best-effort, non-blocking) ───────
    amount = session.get("amount_total")
    currency = session.get("currency") or "usd"
    paid_cents = amount if payment_status == "paid" and amount else None
    try:
        client = _client()
        # Try to get tier from line items if metadata didn't have it.
        if tier_hint not in PAID_PLANS and session.get("id"):
            try:
                line_items = client.checkout.Session.list_line_items(session["id"], limit=1)
                if line_items.data:
                    resolved_from_items = _tier_from_line_item(line_items.data[0])
                    if resolved_from_items:
                        tier_hint = resolved_from_items
            except Exception as exc:
                logger.warning("Could not read checkout line items: %s", exc)

        safe_tier = tier_hint if tier_hint in PAID_PLANS else resolved_tier
        sub = client.Subscription.retrieve(sub_id)
        sub_result = _apply_subscription(
            db,
            sub,
            tier_hint=safe_tier,
            notify=True,
            payment_amount_cents=paid_cents,
            payment_currency=currency,
        )
        logger.info(
            "_apply_checkout_session Phase 2 sub sync: applied=%s reason=%s",
            sub_result.applied,
            sub_result.reason,
        )
    except Exception as exc:
        # Phase 1 already committed the plan — this is non-fatal.
        logger.warning(
            "_apply_checkout_session Phase 2 sub retrieve failed for user %s sub %s: %s",
            user.id,
            sub_id,
            exc,
        )

    return ApplyResult(True, "", user.id)


def sync_from_checkout_session(db: Session, user: User, session_id: str) -> bool:
    """Apply subscription state from a completed Checkout session (post-redirect sync)."""
    if not is_configured():
        logger.warning(
            "sync_from_checkout_session: Stripe not configured, skipping for user %s", user.id
        )
        return False
    if not session_id:
        return False
    try:
        client = _client()
        for attempt in range(5):
            session = client.checkout.Session.retrieve(session_id)
            logger.info(
                "sync_from_checkout_session attempt %d: session=%s payment_status=%s "
                "sub=%s metadata=%s user=%s",
                attempt,
                session_id,
                session.get("payment_status"),
                session.get("subscription"),
                session.get("metadata"),
                user.id,
            )
            if not _session_belongs_to_user(session, user):
                logger.warning(
                    "Checkout session %s customer mismatch for user %s; applying for authenticated user",
                    session_id,
                    user.id,
                )
            result = _apply_checkout_session(db, session, user=user)
            logger.info(
                "sync_from_checkout_session attempt %d result: applied=%s reason=%s",
                attempt,
                result.applied,
                result.reason,
            )
            db.refresh(user)
            logger.info(
                "sync_from_checkout_session after refresh: user=%s plan=%s plan_status=%s "
                "stripe_sub=%s trial_end=%s",
                user.id,
                user.plan,
                user.plan_status,
                user.stripe_subscription_id,
                user.trial_end,
            )
            # Exit as soon as the plan is upgraded — don't wait for stripe_subscription_id
            # to be populated (it may arrive via webhook after this redirect).
            if current_plan(user) in PAID_PLANS:
                return True
            if attempt < 4:
                time.sleep(1.0)
        return current_plan(user) in PAID_PLANS
    except Exception as exc:
        logger.warning("Checkout session sync failed for user %s: %s", user.id, exc)
        return False


def force_sync_user_from_stripe(db: Session, user: User) -> bool:
    """Aggressively sync subscription from Stripe (all customers matching email)."""
    if not is_configured():
        logger.warning(
            "force_sync_user_from_stripe: Stripe not configured, skipping for user %s", user.id
        )
        return False
    updated = False
    try:
        client = _client()
        customer_ids = _stripe_customer_ids_for_user(user)
        logger.info(
            "force_sync_user_from_stripe: user=%s email=%s customer_ids=%s",
            user.id,
            user.email,
            customer_ids,
        )
        if not customer_ids:
            logger.warning(
                "force_sync_user_from_stripe: no Stripe customers found for user %s (%s)",
                user.id,
                user.email,
            )
        for customer_id in customer_ids:
            user.stripe_customer_id = customer_id
            db.commit()
            for status in ("active", "trialing", "past_due", "incomplete"):
                subs = client.Subscription.list(
                    customer=customer_id,
                    status=status,
                    limit=5,
                )
                for sub in subs.data or []:
                    meta = sub.get("metadata") or {}
                    meta_uid = meta.get("user_id")
                    if meta_uid and str(meta_uid) != str(user.id):
                        continue
                    _apply_subscription(db, sub)
                    db.refresh(user)
                    updated = True
                    if current_plan(user) != "trial":
                        return True

            subs = client.Subscription.list(
                customer=customer_id,
                status="all",
                limit=10,
            )
            for sub in subs.data or []:
                if sub.get("status") not in (
                    "active",
                    "trialing",
                    "incomplete",
                    "past_due",
                ):
                    continue
                meta = sub.get("metadata") or {}
                meta_uid = meta.get("user_id")
                if meta_uid and str(meta_uid) != str(user.id):
                    continue
                _apply_subscription(db, sub)
                db.refresh(user)
                updated = True
                if current_plan(user) != "trial":
                    return True
    except Exception as exc:
        logger.warning("Force sync failed for user %s: %s", user.id, exc)
    return updated


def sync_user_subscription(db: Session, user: User) -> bool:
    """Proactively sync the user's subscription from Stripe. Returns True if updated."""
    return force_sync_user_from_stripe(db, user)


# Events that are expected to change a user's plan/status. If one of these is
# received but nothing is applied, the webhook responds non-2xx so the failure is
# visible in the Stripe dashboard (and retried) instead of silently passing.
_PLAN_APPLYING_EVENTS = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "checkout.session.completed",
    "invoice.payment_succeeded",
}


def handle_webhook(db: Session, payload: bytes, sig_header: str) -> dict:
    """Process a Stripe webhook. Returns {type, applied, reason}; the route maps
    a plan-applying event that applied nothing to a non-2xx response."""
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
    result = ApplyResult(True)  # default: non-plan events need no action

    if etype in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        result = _apply_subscription(db, obj, notify=etype == "customer.subscription.created")
    elif etype == "checkout.session.completed":
        session = obj
        if isinstance(obj, dict) and obj.get("id"):
            try:
                session = client.checkout.Session.retrieve(obj["id"])
            except Exception as exc:
                logger.warning("Could not retrieve checkout session for webhook: %s", exc)
        result = _apply_checkout_session(db, session)
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
            sub = client.Subscription.retrieve(sub_id)
            notify = amount_paid > 0 and billing_reason in (
                "subscription_create",
                "subscription_update",
                "subscription_cycle",
            )
            result = _apply_subscription(
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
                applied = sync_user_subscription(db, user)
                result = ApplyResult(applied, "" if applied else "no_subscription_found_for_customer")
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

    if etype in _PLAN_APPLYING_EVENTS and not result.applied:
        logger.warning("Webhook %s did not apply: %s", etype, result.reason)

    return {"type": etype, "applied": result.applied, "reason": result.reason}
