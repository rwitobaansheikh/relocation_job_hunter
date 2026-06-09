"""Global rate limiting + usage accounting for the shared external APIs.

Because Gemini and Hunter run on shared, app-level keys (the hybrid model), the
budget must be enforced across ALL users in this single process. An async
token-bucket paces requests/minute; an ApiUsage row tracks per-day call counts
for the admin dashboard.
"""

import asyncio
import logging
import time
from datetime import datetime

from app.config import settings
from app.database import ApiUsage, SessionLocal

logger = logging.getLogger(__name__)


class _TokenBucket:
    def __init__(self, rate_per_min: int) -> None:
        self.capacity = float(max(1, rate_per_min))
        self.tokens = self.capacity
        self.refill_per_sec = max(1, rate_per_min) / 60.0
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        # Hold the lock across the wait so acquisitions are serialized into a
        # steady, globally-paced stream (exactly what shared keys need).
        async with self._lock:
            while True:
                now = time.monotonic()
                self.tokens = min(
                    self.capacity, self.tokens + (now - self.updated) * self.refill_per_sec
                )
                self.updated = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                await asyncio.sleep((1.0 - self.tokens) / self.refill_per_sec)


_buckets: dict[str, _TokenBucket] = {
    "llm": _TokenBucket(settings.llm_rate_per_min),
    "gemini": _TokenBucket(settings.gemini_rate_per_min),  # legacy alias
    "hunter": _TokenBucket(settings.hunter_rate_per_min),
}


def _record_usage(api: str) -> None:
    day = datetime.utcnow().strftime("%Y-%m-%d")
    db = SessionLocal()
    try:
        row = db.query(ApiUsage).filter(ApiUsage.api == api, ApiUsage.day == day).first()
        if row:
            row.count = (row.count or 0) + 1
        else:
            db.add(ApiUsage(api=api, day=day, count=1))
        db.commit()
    except Exception:  # pragma: no cover - usage accounting must never break calls
        db.rollback()
    finally:
        db.close()


async def acquire(api: str) -> None:
    """Block until a request slot for `api` is available, then record the call."""
    bucket = _buckets.get(api)
    if bucket is not None:
        await bucket.acquire()
    _record_usage(api)
