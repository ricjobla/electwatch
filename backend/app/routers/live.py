from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.election import Election
from app.schemas import CalendarElectionOut, LiveElectionsResponse

router = APIRouter(tags=["live"])


def _row(election: Election) -> CalendarElectionOut:
    return CalendarElectionOut(
        id=election.id,
        title=election.title,
        election_date=election.election_date,
        status=election.status,
        type=election.type,
        country_id=election.country_id,
        country_name=election.country.name if election.country else None,
        turnout_pct=election.turnout_pct,
        reporting_pct=election.reporting_pct,
    )


@router.get("/live", response_model=LiveElectionsResponse)
def list_live_elections(db: Session = Depends(get_db)):
    """Elections currently in ``live`` tally mode (partial results)."""
    stmt = (
        select(Election)
        .options(joinedload(Election.country))
        .where(Election.status == "live")
        .order_by(Election.election_date)
    )
    elections = db.scalars(stmt).all()
    return LiveElectionsResponse(elections=[_row(e) for e in elections])
