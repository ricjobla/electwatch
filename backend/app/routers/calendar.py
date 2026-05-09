from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import CalendarElectionOut, CalendarResponse
from app.services.election_query import list_elections

router = APIRouter(tags=["calendar"])


def _calendar_row(election) -> CalendarElectionOut:
    return CalendarElectionOut(
        id=election.id,
        title=election.title,
        election_date=election.election_date,
        status=election.status,
        type=election.type,
        country_id=election.country_id,
        country_name=election.country.name if election.country else None,
        turnout_pct=election.turnout_pct,
    )


@router.get("/calendar", response_model=CalendarResponse)
def get_calendar(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    status: str | None = Query(None, description="upcoming | live | complete"),
    region: str | None = Query(
        None, description="Substring match on countries.region (e.g. europe)"
    ),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    try:
        elections = list_elections(
            db,
            date_from=date_from,
            date_to=date_to,
            status=status,
            region=region,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return CalendarResponse(
        elections=[_calendar_row(e) for e in elections],
    )
