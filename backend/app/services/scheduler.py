"""APScheduler-based background loop that drives per-user automation.

A single recurring tick checks which users are due (by their configured
interval) and runs their pipeline. Jobs are persisted in the same database via
SQLAlchemyJobStore so the schedule survives restarts (single-worker EC2).
"""

import logging

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.database import SessionLocal
from app.services.automation import run_due_loops

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_TICK_JOB_ID = "automation_tick"


async def _tick() -> None:
    """One scheduler tick: run automation for any loops that are due."""
    db = SessionLocal()
    try:
        processed = await run_due_loops(db)
        if processed:
            logger.info("Automation tick processed %d loop(s)", processed)
        from app.services.trial_notifications import process_trial_notifications

        notified = await process_trial_notifications(db)
        if notified:
            logger.info("Trial notifications sent to %d user(s)", notified)
    except Exception:  # pragma: no cover - never let a tick crash the loop
        logger.exception("Automation tick failed")
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None or not settings.scheduler_enabled:
        return
    jobstores = {"default": SQLAlchemyJobStore(url=settings.database_url)}
    _scheduler = AsyncIOScheduler(jobstores=jobstores, timezone="UTC")
    _scheduler.add_job(
        _tick,
        trigger="interval",
        minutes=max(1, settings.scheduler_tick_minutes),
        id=_TICK_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "Automation scheduler started (tick every %d min)", settings.scheduler_tick_minutes
    )


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
