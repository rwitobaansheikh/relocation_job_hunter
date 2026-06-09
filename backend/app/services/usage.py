"""Per-user, per-day send accounting used to enforce plan caps.

scope is "manual" for hand-sent outreach (one job send = 1, regardless of how
many contacts are emailed) or "loop:{loop_id}" for an automation loop.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.database import UsageCounter


def today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def get_usage(db: Session, profile_id: int, scope: str) -> int:
    row = (
        db.query(UsageCounter)
        .filter(
            UsageCounter.user_profile_id == profile_id,
            UsageCounter.day == today_str(),
            UsageCounter.scope == scope,
        )
        .first()
    )
    return row.count if row else 0


def incr_usage(db: Session, profile_id: int, scope: str, n: int = 1) -> int:
    day = today_str()
    row = (
        db.query(UsageCounter)
        .filter(
            UsageCounter.user_profile_id == profile_id,
            UsageCounter.day == day,
            UsageCounter.scope == scope,
        )
        .first()
    )
    if row:
        row.count = (row.count or 0) + n
    else:
        row = UsageCounter(user_profile_id=profile_id, day=day, scope=scope, count=n)
        db.add(row)
    db.flush()
    return row.count
