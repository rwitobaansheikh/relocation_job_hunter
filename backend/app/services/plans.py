"""Subscription plans: limits, effective-plan resolution, and display currency.

This is the single source of truth for what each tier is allowed to do. The
actual money is charged by Stripe (Adaptive Pricing converts the USD price into
the buyer's local currency at Checkout); the FX table here is only used to show
an *estimated* local price in the UI.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Limits:
    plan: str
    max_loops: int
    auto_per_loop_per_day: int
    manual_per_day: int
    tailor_per_day: int
    llm_per_day: int

    @property
    def can_automate(self) -> bool:
        return self.max_loops > 0


# Hard ceiling on automation loops for everyone, including superusers.
MAX_LOOPS_HARD_CAP = 5

PAID_PLANS = ("basic", "standard", "pro")

PLAN_LIMITS: dict[str, Limits] = {
    # 3-day free trial mirrors Basic.
    "trial": Limits("trial", max_loops=1, auto_per_loop_per_day=5, manual_per_day=20, tailor_per_day=10, llm_per_day=50),
    "basic": Limits("basic", max_loops=1, auto_per_loop_per_day=5, manual_per_day=20, tailor_per_day=10, llm_per_day=50),
    "standard": Limits("standard", max_loops=3, auto_per_loop_per_day=20, manual_per_day=100, tailor_per_day=50, llm_per_day=250),
    "pro": Limits("pro", max_loops=5, auto_per_loop_per_day=25, manual_per_day=300, tailor_per_day=150, llm_per_day=1000),
    # Lapsed trial / canceled subscription: locked until they subscribe.
    "expired": Limits("expired", max_loops=0, auto_per_loop_per_day=0, manual_per_day=0, tailor_per_day=0, llm_per_day=0),
}

# Admin "unlimited access" override (still capped at 5 loops, still subject to
# the shared-API global rate limiter).
_BIG = 100_000
UNLIMITED = Limits("unlimited", max_loops=MAX_LOOPS_HARD_CAP, auto_per_loop_per_day=_BIG, manual_per_day=_BIG, tailor_per_day=_BIG, llm_per_day=_BIG)

# Tier catalog shown on the billing/pricing page (USD base price).
TIERS: list[dict] = [
    {
        "id": "basic",
        "name": "Basic",
        "price_usd": 15,
        "features": [
            "1 automation loop for 1 job role",
            "Up to 5 automated applications per day",
            "Up to 20 manual applications per day",
        ],
    },
    {
        "id": "standard",
        "name": "Standard",
        "price_usd": 25,
        "features": [
            "3 automation loops for 3 job roles",
            "Up to 20 automated applications per loop per day",
            "Up to 100 manual applications per day",
        ],
    },
    {
        "id": "pro",
        "name": "Pro",
        "price_usd": 45,
        "features": [
            "5 automation loops for 5 job roles",
            "Up to 25 automated applications per loop per day",
            "Up to 300 manual applications per day",
        ],
    },
]


def current_plan(user) -> str:
    """Resolve a user's effective plan id: unlimited | basic | standard | pro |
    trial | expired."""
    if getattr(user, "unlimited_access", False) or getattr(user, "role", "") == "admin":
        return "unlimited"
    plan = (getattr(user, "plan", "") or "").lower()
    status = (getattr(user, "plan_status", "") or "").lower()
    if plan in PAID_PLANS and status in ("active", "trialing"):
        return plan
    trial_end = getattr(user, "trial_end", None)
    if trial_end and datetime.utcnow() < trial_end:
        return "trial"
    return "expired"


def effective_limits(user) -> Limits:
    plan = current_plan(user)
    if plan == "unlimited":
        return UNLIMITED
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["expired"])


# --------------------------------------------------------------------------- #
# Display currency (estimate only; Stripe Adaptive Pricing does the real charge)
# --------------------------------------------------------------------------- #
# country code -> (currency, symbol, approximate units per 1 USD)
_COUNTRY_CURRENCY: dict[str, tuple[str, str, float]] = {
    "US": ("USD", "$", 1.0),
    "GB": ("GBP", "£", 0.79),
    "IN": ("INR", "₹", 83.0),
    "CA": ("CAD", "C$", 1.36),
    "AU": ("AUD", "A$", 1.52),
    "AE": ("AED", "AED ", 3.67),
    "CH": ("CHF", "CHF ", 0.90),
    "JP": ("JPY", "¥", 157.0),
    "SG": ("SGD", "S$", 1.35),
    "BR": ("BRL", "R$", 5.4),
    "ZA": ("ZAR", "R", 18.5),
    "NZ": ("NZD", "NZ$", 1.66),
    "SE": ("SEK", "kr ", 10.6),
    "NO": ("NOK", "kr ", 10.8),
    "DK": ("DKK", "kr ", 6.9),
    "PL": ("PLN", "zł ", 4.0),
}
# Eurozone members all display in EUR.
_EUR_COUNTRIES = {
    "DE", "FR", "ES", "IT", "NL", "IE", "PT", "AT", "BE", "FI", "GR", "LU",
    "SK", "SI", "EE", "LV", "LT", "CY", "MT", "HR",
}
_DEFAULT = ("USD", "$", 1.0)


def localized_price(usd: float, country: Optional[str]) -> dict:
    """Best-effort local-currency estimate for display. Falls back to USD."""
    code = (country or "").upper()
    if code in _EUR_COUNTRIES:
        currency, symbol, fx = ("EUR", "€", 0.92)
    else:
        currency, symbol, fx = _COUNTRY_CURRENCY.get(code, _DEFAULT)
    amount = usd * fx
    # Whole units for big-denomination currencies, otherwise nearest integer.
    rounded = int(round(amount))
    return {
        "currency": currency,
        "symbol": symbol,
        "amount": rounded,
        "display": f"{symbol}{rounded:,}",
        "is_estimate": currency != "USD",
    }
