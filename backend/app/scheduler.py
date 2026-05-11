"""APScheduler jobs for live election scraping (Phase 3)."""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.ingest.scrapers import SCRAPER_CLASSES, scraper_for_country
from app.models.election import Election

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def scheduler_enabled() -> bool:
    return os.getenv("SCRAPER_SCHEDULER_ENABLED", "").lower() in ("1", "true", "yes")


def run_live_poll_cycle() -> None:
    """Poll official sites for configured countries while elections are upcoming/live."""
    db = SessionLocal()
    try:
        today = date.today()
        horizon_start = today - timedelta(days=21)
        elections = (
            db.query(Election)
            .filter(Election.country_id.in_(list(SCRAPER_CLASSES.keys())))
            .filter(Election.status.in_(("upcoming", "live")))
            .filter(Election.election_date <= today)
            .filter(Election.election_date >= horizon_start)
            .all()
        )
        for election in elections:
            scraper_cls = scraper_for_country(election.country_id)
            if scraper_cls is None:
                continue
            scraper_cls(election.id, db).run()
    except Exception:
        log.exception("live poll cycle failed")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    if not scheduler_enabled():
        log.info("SCRAPER_SCHEDULER_ENABLED not set — live scrape scheduler idle")
        return None
    if _scheduler is not None:
        return _scheduler
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(
        run_live_poll_cycle,
        "interval",
        minutes=5,
        id="electwatch_live_scrape",
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    log.info("Started APScheduler — live scrape every 5 minutes")
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    log.info("Stopped APScheduler")
