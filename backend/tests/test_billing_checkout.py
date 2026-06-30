"""Billing checkout sync tests."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.billing import (
    _apply_checkout_session,
    _session_belongs_to_user,
    sync_from_checkout_session,
)
from app.services.plans import current_plan


class FakeUser:
    id = 42
    email = "user@example.com"
    stripe_customer_id = ""
    stripe_subscription_id = ""
    plan = "trial"
    plan_status = "trialing"
    trial_end = datetime.utcnow() + timedelta(days=3)
    current_period_end = None
    subscription_email_key = ""


def test_session_belongs_to_user():
    user = FakeUser()
    session = {"metadata": {"user_id": "42"}, "client_reference_id": "42"}
    assert _session_belongs_to_user(session, user) is True

    session = {"metadata": {"user_id": "99"}, "client_reference_id": "99"}
    assert _session_belongs_to_user(session, user) is False


def test_apply_checkout_session_sets_paid_plan_immediately():
    user = FakeUser()
    db = MagicMock()

    session = {
        "id": "cs_test_123",
        "customer": "cus_abc",
        "subscription": "sub_abc",
        "metadata": {"user_id": "42", "tier": "basic"},
        "client_reference_id": "42",
        "payment_status": "paid",
        "amount_total": 1500,
        "currency": "usd",
    }

    sub = {
        "id": "sub_abc",
        "customer": "cus_abc",
        "status": "active",
        "metadata": {"user_id": "42", "tier": "basic"},
        "items": {"data": [{"price": "price_basic"}]},
    }

    with patch("app.services.billing._resolve_user", return_value=user), patch(
        "app.services.billing._client"
    ) as mock_client, patch("app.services.billing.settings") as mock_settings:
        mock_settings.stripe_price_basic = "price_basic"
        mock_settings.stripe_price_standard = "price_standard"
        mock_settings.stripe_price_pro = "price_pro"
        client = mock_client.return_value
        client.Subscription.retrieve.return_value = sub

        _apply_checkout_session(db, session)

    assert user.plan == "basic"
    assert user.trial_end is None
    assert user.stripe_subscription_id == "sub_abc"
    assert user.stripe_customer_id == "cus_abc"
    assert current_plan(user) == "basic"


def test_current_plan_never_shows_trial_when_stripe_linked():
    user = FakeUser()
    user.stripe_subscription_id = "sub_abc"
    user.plan_status = "active"
    user.plan = "trial"  # stale column
    assert current_plan(user) == "basic"


def test_sync_from_checkout_session_retries_until_upgraded():
    user = FakeUser()
    db = MagicMock()
    db.refresh = MagicMock()

    session = {
        "id": "cs_test_123",
        "customer": "cus_abc",
        "subscription": "sub_abc",
        "metadata": {"user_id": "42", "tier": "standard"},
        "client_reference_id": "42",
        "payment_status": "paid",
    }

    with patch("app.services.billing.is_configured", return_value=True), patch(
        "app.services.billing._client"
    ) as mock_client, patch(
        "app.services.billing._apply_checkout_session",
        side_effect=lambda _db, _session: setattr(user, "stripe_subscription_id", "sub_abc")
        or setattr(user, "plan", "standard")
        or setattr(user, "trial_end", None),
    ), patch("app.services.billing.time.sleep"):
        mock_client.return_value.checkout.Session.retrieve.return_value = session
        ok = sync_from_checkout_session(db, user, "cs_test_123")

    assert ok is True
    assert user.plan == "standard"
