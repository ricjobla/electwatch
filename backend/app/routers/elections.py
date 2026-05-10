from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.election import Election
from app.schemas import (
    CalendarElectionOut,
    ElectionDetailOut,
    ElectionResultRow,
    ElectionsListResponse,
)
from app.services.election_query import (
    distinct_election_types,
    get_election_with_results,
    list_elections,
)

router = APIRouter(tags=["elections"])


def _calendar_row(election: Election) -> CalendarElectionOut:
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


@router.get("/elections", response_model=ElectionsListResponse)
def list_elections_api(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    status: str | None = None,
    region: str | None = None,
    country_id: str | None = None,
    election_type: str | None = Query(
        None,
        alias="type",
        description="Case-insensitive substring of elections.type",
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
            country_id=country_id,
            election_type=election_type,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return ElectionsListResponse(elections=[_calendar_row(e) for e in elections])


def _election_results_rows(election: Election) -> list[ElectionResultRow]:
    rows: list[ElectionResultRow] = []
    for r in sorted(election.results, key=lambda x: (x.vote_share or 0), reverse=True):
        party = r.party
        rows.append(
            ElectionResultRow(
                vote_share=r.vote_share,
                seats_won=r.seats_won,
                votes_raw=r.votes_raw,
                party_id=r.party_id,
                party_name=party.name if party else None,
                party_short_name=party.short_name if party else None,
                party_color_hex=party.color_hex if party else None,
            )
        )
    return rows


@router.get("/elections/types", response_model=list[str])
def get_election_types(db: Session = Depends(get_db)):
    """Distinct, non-empty values of ``Election.type`` for filter dropdowns."""
    return distinct_election_types(db)


@router.get("/elections/{election_id}/results", response_model=list[ElectionResultRow])
def get_election_results(election_id: str, db: Session = Depends(get_db)):
    election = get_election_with_results(db, election_id)
    if election is None:
        raise HTTPException(status_code=404, detail="Election not found")
    return _election_results_rows(election)


@router.get("/elections/{election_id}", response_model=ElectionDetailOut)
def get_election(election_id: str, db: Session = Depends(get_db)):
    election = get_election_with_results(db, election_id)
    if election is None:
        raise HTTPException(status_code=404, detail="Election not found")

    results = _election_results_rows(election)

    return ElectionDetailOut(
        id=election.id,
        title=election.title,
        election_date=election.election_date,
        status=election.status,
        type=election.type,
        country_id=election.country_id,
        description=election.description,
        wikipedia_url=election.wikipedia_url,
        wikidata_id=election.wikidata_id,
        turnout_pct=election.turnout_pct,
        source_url=election.source_url,
        last_updated=election.last_updated,
        country=election.country,
        results=results,
    )
