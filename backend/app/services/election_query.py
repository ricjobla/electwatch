from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.country import Country
from app.models.election import Election
from app.models.result import Result

_VALID_STATUS = frozenset({"upcoming", "live", "complete"})


def list_elections(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    status: str | None = None,
    region: str | None = None,
    country_id: str | None = None,
    limit: int = 500,
) -> list[Election]:
    stmt = (
        select(Election)
        .options(joinedload(Election.country))
        .order_by(Election.election_date.asc(), Election.id.asc())
    )

    if region:
        stmt = stmt.join(Country, Election.country_id == Country.id).where(
            Country.region.contains(region)
        )

    if date_from is not None:
        stmt = stmt.where(Election.election_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Election.election_date <= date_to)

    if status:
        if status not in _VALID_STATUS:
            raise ValueError(
                f"status must be one of {sorted(_VALID_STATUS)}, got {status!r}"
            )
        stmt = stmt.where(Election.status == status)

    if country_id:
        stmt = stmt.where(Election.country_id == country_id.upper())

    stmt = stmt.limit(min(limit, 2000))
    return list(db.scalars(stmt).unique().all())


def get_election_with_results(db: Session, election_id: str) -> Election | None:
    stmt = (
        select(Election)
        .where(Election.id == election_id)
        .options(
            joinedload(Election.country),
            selectinload(Election.results).joinedload(Result.party),
        )
    )
    return db.scalars(stmt).unique().one_or_none()
