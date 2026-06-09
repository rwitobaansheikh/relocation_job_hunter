"""Cryptographic helpers: password hashing and at-rest secret encryption.

Kept dependency-light (no DB imports) so it can be used from both the auth
layer and the database bootstrap without circular imports.
"""

import base64
import hashlib
import logging
from functools import lru_cache

import bcrypt
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    # bcrypt has a hard 72-byte limit; encode then slice on bytes so long or
    # multi-byte passwords don't raise instead of being accepted.
    pw = (password or "").encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        pw = (password or "").encode("utf-8")[:72]
        return bcrypt.checkpw(pw, password_hash.encode("utf-8"))
    except Exception:  # pragma: no cover - malformed hash
        return False


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Build the Fernet cipher from the configured key, or derive one from the
    JWT secret as a dev fallback (with a warning)."""
    raw = (settings.encryption_key or "").strip()
    if raw:
        try:
            return Fernet(raw.encode())
        except Exception:
            logger.warning("ENCRYPTION_KEY is not a valid Fernet key; deriving one from it.")
            key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
            return Fernet(key)
    logger.warning(
        "ENCRYPTION_KEY not set; deriving a key from JWT_SECRET. Set ENCRYPTION_KEY in production."
    )
    derived = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret.encode()).digest())
    return Fernet(derived)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret for storage. Empty input -> empty output."""
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt a stored secret. Returns "" on empty/invalid input."""
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        logger.warning("Failed to decrypt a stored secret (key changed?).")
        return ""
