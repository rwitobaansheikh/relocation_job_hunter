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

        _apply_checkout_session(db, session, user=user)

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


def test_current_plan_prefers_paid_plan_column():
    user = FakeUser()
    user.plan = "standard"
    user.trial_end = datetime.utcnow() + timedelta(days=3)
    assert current_plan(user) == "standard"


def test_apply_checkout_session_sends_confirmation_email_once():
    user = FakeUser()
    user.subscription_email_key = ""
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
    ) as mock_client, patch("app.services.billing.settings") as mock_settings, patch(
        "app.services.billing._schedule_system_email"
    ) as mock_send:
        mock_settings.stripe_price_basic = "price_basic"
        mock_settings.stripe_price_standard = "price_standard"
        mock_settings.stripe_price_pro = "price_pro"
        mock_client.return_value.Subscription.retrieve.return_value = sub

        _apply_checkout_session(db, session, user=user)
        assert mock_send.call_count == 1
        to = mock_send.call_args[0][0]
        assert to == user.email

        # Re-applying the same checkout (e.g. webhook after redirect) must not
        # send a duplicate email.
        _apply_checkout_session(db, session, user=user)
        assert mock_send.call_count == 1


def test_sync_from_checkout_session_single_pass_no_sleep():
    """The post-redirect sync must not block the request thread with retries."""
    user = FakeUser()
    user.plan = "trial"
    db = MagicMock()

    session = {
        "id": "cs_test_123",
        "metadata": {"user_id": "42"},
        "client_reference_id": "42",
        "payment_status": "paid",
    }

    apply_mock = MagicMock()  # leaves user on trial — previously triggered retries
    with patch("app.services.billing.is_configured", return_value=True), patch(
        "app.services.billing._client"
    ) as mock_client, patch(
        "app.services.billing._apply_checkout_session", apply_mock
    ), patch(
        "app.services.billing.time.sleep",
        side_effect=AssertionError("sync_from_checkout_session must not sleep"),
    ):
        mock_client.return_value.checkout.Session.retrieve.return_value = session
        ok = sync_from_checkout_session(db, user, "cs_test_123")

    assert ok is False
    assert apply_mock.call_count == 1


def test_apply_subscription_unresolved_tier_falls_back_to_basic():
    """A paid subscription whose tier can't be resolved must still provision."""
    from app.services.billing import _apply_subscription

    user = FakeUser()
    user.plan = "trial"
    user.trial_end = datetime.utcnow() + timedelta(days=3)
    db = MagicMock()

    sub = {
        "id": "sub_abc",
        "customer": "cus_abc",
        "status": "active",
        "metadata": {"user_id": "42"},  # no tier
        "items": {"data": [{"price": "price_unknown"}]},
    }

    with patch("app.services.billing._resolve_user", return_value=user), patch(
        "app.services.billing.is_configured", return_value=False
    ), patch("app.services.billing.settings") as mock_settings:
        mock_settings.stripe_price_basic = "price_basic"
        mock_settings.stripe_price_standard = "price_standard"
        mock_settings.stripe_price_pro = "price_pro"
        _apply_subscription(db, sub)

    assert user.plan == "basic"
    assert user.trial_end is None
    assert user.plan_status == "active"


def test_create_checkout_session_uses_idempotency_key_and_sub_guard():
    from app.services.billing import BillingError, create_checkout_session

    user = FakeUser()
    user.stripe_customer_id = "cus_abc"
    db = MagicMock()

    with patch("app.services.billing._client") as mock_client, patch(
        "app.services.billing.settings"
    ) as mock_settings:
        mock_settings.stripe_price_basic = "price_basic"
        mock_settings.stripe_price_standard = "price_standard"
        mock_settings.stripe_price_pro = "price_pro"
        mock_settings.app_base_url = "https://example.com"
        client = mock_client.return_value
        client.Subscription.list.return_value = MagicMock(data=[])
        client.checkout.Session.create.return_value = {"url": "https://stripe/checkout"}

        url = create_checkout_session(db, user, "basic")
        assert url == "https://stripe/checkout"
        kwargs = client.checkout.Session.create.call_args.kwargs
        assert kwargs["idempotency_key"].startswith("checkout:42:basic:pay:")

        # An existing active subscription must block a second checkout.
        client.Subscription.list.return_value = MagicMock(data=[{"id": "sub_live"}])
        try:
            create_checkout_session(db, user, "basic")
            assert False, "expected BillingError"
        except BillingError:
            pass


def test_ensure_customer_reuses_existing_by_email():
    from app.services.billing import _ensure_customer

    user = FakeUser()
    user.stripe_customer_id = ""
    db = MagicMock()

    with patch(
        "app.services.billing._stripe_customer_ids_for_user",
        return_value=["cus_existing"],
    ), patch("app.services.billing._client") as mock_client:
        cid = _ensure_customer(db, user)

    assert cid == "cus_existing"
    assert user.stripe_customer_id == "cus_existing"
    mock_client.return_value.Customer.create.assert_not_called()


def test_checkout_route_rejects_when_already_subscribed():
    from fastapi import HTTPException

    from app.routes_billing import checkout
    from app.schemas import CheckoutRequest

    user = FakeUser()
    user.stripe_subscription_id = "sub_live"
    user.plan_status = "active"
    try:
        checkout(CheckoutRequest(tier="standard"), user=user, db=MagicMock())
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "already have an active subscription" in exc.detail


def test_subscription_email_dedupe_is_atomic_against_concurrent_callers():
    """Two concurrent apply paths (redirect sync + webhook) send exactly one email."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base, User
    from app.services.billing import _maybe_send_subscription_email

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    setup = Session()
    u = User(email="user@example.com", password_hash="x", plan="basic", plan_status="active")
    setup.add(u)
    setup.commit()
    uid = u.id
    setup.close()

    sends = []
    with patch(
        "app.services.billing._schedule_system_email",
        side_effect=lambda *a: sends.append(a),
    ):
        for _ in range(2):  # same event applied twice (webhook retry / race)
            s = Session()
            user = s.query(User).filter(User.id == uid).first()
            _maybe_send_subscription_email(
                s,
                user,
                tier="basic",
                subscription_id="sub_abc",
                status="active",
                payment_amount_cents=1500,
            )
            s.close()

    assert len(sends) == 1


def test_send_system_email_uses_resend_when_configured():
    import asyncio

    from app.services import system_email

    captured = {}

    class FakeResponse:
        status_code = 200
        text = "{}"

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

    with patch.object(system_email.settings, "resend_api_key", "re_test_key"), patch.object(
        system_email.httpx, "AsyncClient", FakeAsyncClient
    ):
        ok, err = asyncio.run(
            system_email.send_system_email("to@example.com", "Hello", "Body text", "<p>Body</p>")
        )

    assert ok is True and err is None
    assert captured["json"]["from"] == "Job Application Flow <email@jobapplicationflow.com>"
    assert captured["json"]["to"] == ["to@example.com"]
    assert captured["headers"]["Authorization"] == "Bearer re_test_key"


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

    def _apply_side_effect(_db, _session, user=None):
        target = user or FakeUser()
        target.stripe_subscription_id = "sub_abc"
        target.plan = "standard"
        target.trial_end = None

    with patch("app.services.billing.is_configured", return_value=True), patch(
        "app.services.billing._client"
    ) as mock_client, patch(
        "app.services.billing._apply_checkout_session",
        side_effect=_apply_side_effect,
    ), patch("app.services.billing.time.sleep"):
        mock_client.return_value.checkout.Session.retrieve.return_value = session
        ok = sync_from_checkout_session(db, user, "cs_test_123")

    assert ok is True
    assert user.plan == "standard"
