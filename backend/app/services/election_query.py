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
    election_type: str | None = None,
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

    if election_type:
        # Election.type is a free-form string from ParlGov (parliamentary,
        # presidential, european_parliament, ...) plus None from Wikidata.
        # We match case-insensitively as a substring so callers can pass either
        # 'parliamentary' or 'parliament' and find the row.
        normalized = election_type.strip().lower()
        if normalized:
            stmt = stmt.where(Election.type.ilike(f"%{normalized}%"))

    stmt = stmt.limit(min(limit, 2000))
    return list(db.scalars(stmt).unique().all())


def distinct_election_types(db: Session) -> list[str]:
    """Sorted distinct, non-empty values of ``Election.type``.

    Used by the frontend to populate the type filter dropdown.
    """
    rows = db.scalars(
        select(Election.type).where(Election.type.isnot(None)).distinct()
    ).all()
    return sorted({(t or "").strip() for t in rows if (t or "").strip()})


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
