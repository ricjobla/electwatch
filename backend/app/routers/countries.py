from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.country import Country
from app.schemas import CalendarElectionOut, CountriesResponse, ElectionsListResponse
from app.services.election_query import list_elections

router = APIRouter(tags=["countries"])


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


@router.get("/countries", response_model=CountriesResponse)
def get_countries(db: Session = Depends(get_db)):
    stmt = select(Country).order_by(Country.name.asc())
    countries = list(db.scalars(stmt).all())
    return CountriesResponse(countries=countries)


@router.get("/countries/{iso_code}/elections", response_model=ElectionsListResponse)
def get_country_elections(
    iso_code: str,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    iso = iso_code.strip().upper()
    if len(iso) != 2:
        raise HTTPException(status_code=422, detail="ISO code must be two letters")

    country = db.get(Country, iso)
    if country is None:
        raise HTTPException(status_code=404, detail="Country not found")

    try:
        elections = list_elections(
            db,
            date_from=date_from,
            date_to=date_to,
            country_id=iso,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ElectionsListResponse(elections=[_calendar_row(e) for e in elections])
