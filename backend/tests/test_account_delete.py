"""Account deletion tests — OAuth users have no usable password."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.routes import delete_my_account
from app.schemas import DeleteAccountRequest


class FakeUser:
    id = 7
    email = "user@example.com"
    oauth_provider = ""
    password_hash = "hashed"


def test_oauth_user_can_delete_with_confirm_only():
    user = FakeUser()
    user.oauth_provider = "google"
    with patch("app.routes.delete_account") as mock_delete:
        delete_my_account(
            DeleteAccountRequest(password="", confirm="DELETE"), user=user, db=MagicMock()
        )
    mock_delete.assert_called_once()


def test_oauth_user_delete_requires_confirm():
    user = FakeUser()
    user.oauth_provider = "google"
    with patch("app.routes.delete_account") as mock_delete:
        with pytest.raises(HTTPException) as exc:
            delete_my_account(
                DeleteAccountRequest(password="", confirm=""), user=user, db=MagicMock()
            )
    assert exc.value.status_code == 400
    mock_delete.assert_not_called()


def test_password_user_still_requires_correct_password():
    user = FakeUser()
    with patch("app.routes.delete_account") as mock_delete, patch(
        "app.routes.verify_password", return_value=False
    ):
        with pytest.raises(HTTPException) as exc:
            delete_my_account(
                DeleteAccountRequest(password="wrong", confirm="DELETE"),
                user=user,
                db=MagicMock(),
            )
    assert exc.value.status_code == 403
    mock_delete.assert_not_called()


def test_password_user_deletes_with_correct_password():
    user = FakeUser()
    with patch("app.routes.delete_account") as mock_delete, patch(
        "app.routes.verify_password", return_value=True
    ):
        delete_my_account(
            DeleteAccountRequest(password="right", confirm="DELETE"),
            user=user,
            db=MagicMock(),
        )
    mock_delete.assert_called_once()
