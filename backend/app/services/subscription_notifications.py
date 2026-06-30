"""Subscription confirmation emails sent from email@jobapplicationflow.com."""

from app.config import settings
from app.database import User
from app.services.plans import PAID_PLANS, TIERS

_TIER_NAMES = {t["id"]: t["name"] for t in TIERS}


def _billing_url() -> str:
    return f"{settings.app_base_url.rstrip('/')}/app/billing"


def _tier_label(tier: str) -> str:
    return _TIER_NAMES.get(tier, tier.capitalize())


def subscription_email_key(subscription_id: str, tier: str, *, paid: bool = False) -> str:
    suffix = ":paid" if paid else ""
    return f"{subscription_id}:{tier}{suffix}"


def send_subscription_confirmation_email(
    user: User,
    tier: str,
    *,
    payment_amount_cents: int | None = None,
    payment_currency: str = "usd",
    trialing: bool = False,
) -> tuple[str, str, str, str | None]:
    """Return (to, subject, text, html) for a successful subscription."""
    plan_name = _tier_label(tier)
    to = user.email

    if trialing:
        subject = f"Your {plan_name} free trial is active — Job Application Flow"
        payment_line = (
            f"Your {settings.trial_days}-day free trial on the {plan_name} plan is now active. "
            f"Your saved payment method will be charged when the trial ends unless you cancel."
        )
    elif payment_amount_cents and payment_amount_cents > 0:
        amount = payment_amount_cents / 100
        currency = payment_currency.upper()
        subject = f"Payment received — your {plan_name} subscription is active"
        payment_line = (
            f"Thank you — we received your payment ({currency} {amount:,.2f}). "
            f"Your {plan_name} subscription is now active."
        )
    else:
        subject = f"Your {plan_name} subscription is active — Job Application Flow"
        payment_line = f"Your {plan_name} subscription is now active."

    text = (
        f"Hi,\n\n"
        f"{payment_line}\n\n"
        f"You can manage your plan anytime from the billing page:\n"
        f"{_billing_url()}\n\n"
        f"— Job Application Flow"
    )
    html = (
        f"<p>Hi,</p>"
        f"<p>{payment_line}</p>"
        f'<p><a href="{_billing_url()}">Manage your subscription →</a></p>'
        f"<p>— Job Application Flow</p>"
    )
    return to, subject, text, html


def should_send_subscription_email(user: User, tier: str, email_key: str) -> bool:
    if tier not in PAID_PLANS:
        return False
    return getattr(user, "subscription_email_key", "") != email_key
