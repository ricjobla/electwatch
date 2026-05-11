"""Dev/debug admin routes (guarded by ``ELECTWATCH_DEBUG``)."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.ingest.scrapers import scraper_for_country
from app.models.election import Election
from app.models.ingest_log import IngestLog
from app.scheduler import run_live_poll_cycle
from app.schemas import IngestLogRow

router = APIRouter(prefix="/admin", tags=["admin"])


def debug_enabled() -> bool:
    return os.getenv("ELECTWATCH_DEBUG", "").lower() in ("1", "true", "yes")


def _require_debug() -> None:
    if not debug_enabled():
        raise HTTPException(status_code=403, detail="Admin routes disabled")


@router.get("/ingest-log", response_model=list[IngestLogRow])
def list_ingest_log(limit: int = 200, db: Session = Depends(get_db)):
    _require_debug()
    stmt = select(IngestLog).order_by(IngestLog.run_at.desc()).limit(min(limit, 2000))
    return list(db.scalars(stmt).all())


@router.post("/scrape/{election_id}")
def trigger_scrape(election_id: str, db: Session = Depends(get_db)):
    """Run the country scraper once for a single election."""
    _require_debug()
    election = db.get(Election, election_id)
    if election is None:
        raise HTTPException(status_code=404, detail="Election not found")
    scraper_cls = scraper_for_country(election.country_id)
    if scraper_cls is None:
        raise HTTPException(status_code=422, detail="No scraper for this country")
    scraper_cls(election_id, db).run()
    return {"ok": True, "election_id": election_id}


@router.post("/poll-live")
def trigger_full_poll():
    """Run the same cycle as the 5-minute scheduler job."""
    _require_debug()
    run_live_poll_cycle()
    return {"ok": True}
