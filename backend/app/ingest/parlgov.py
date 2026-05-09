"""Download ParlGov CSV bundle and upsert European elections, parties, and results."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import date, datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.country import Country
from app.models.election import Election
from app.models.ingest_log import IngestLog
from app.models.party import Party
from app.models.result import Result

# Spec naming; the hosted zip at this path currently 404s — see FALLBACK_ZIP_URL.
PRIMARY_ZIP_URL = "http://www.parlgov.org/data/parlgov-development.csv.zip"
FALLBACK_ZIP_URL = "https://www.parlgov.org/data/parlgov-development_csv-utf-8.zip"

VIEW_ELECTION = "view_election.csv"
ISO_TABLE = "external_country_iso.csv"

# ParlGov marks some countries outside "Europe" (e.g. Russia → Asia) but they are in scope
# for a European elections dashboard.
EXTRA_EUROPEAN_ISO2: frozenset[str] = frozenset({"RU"})

COMMIT_EVERY = 500


def _slug_region(region: str | None) -> str:
    if not region:
        return "europe"
    s = region.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_") or "europe"


def _norm_election_type(raw: str | None) -> str | None:
    if not raw:
        return None
    r = raw.strip().lower()
    if r == "parliament":
        return "parliamentary"
    if r == "ep":
        return "european_parliament"
    return r


def _parse_float(val: str | None) -> float | None:
    if val is None:
        return None
    v = val.strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _parse_int(val: str | None) -> int | None:
    if val is None:
        return None
    v = val.strip()
    if not v:
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    v = val.strip()
    if not v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


def download_parlgov_zip(client: httpx.Client, url: str = PRIMARY_ZIP_URL) -> bytes:
    try:
        response = client.get(url)
        response.raise_for_status()
        return response.content
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404 and url == PRIMARY_ZIP_URL:
            return download_parlgov_zip(client, FALLBACK_ZIP_URL)
        raise


def load_iso_mappings(zip_bytes: bytes) -> tuple[dict[str, dict[str, Any]], frozenset[str]]:
    """ISO3 → metadata row; set of ISO2 codes classified as Europe (+ extras)."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        raw = zf.read(ISO_TABLE).decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(raw))
    iso3_to_row: dict[str, dict[str, Any]] = {}
    europe_iso2: set[str] = set()

    for row in reader:
        row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        iso2 = row.get("iso2") or ""
        iso3 = row.get("iso3") or ""
        if len(iso3) == 3 and len(iso2) == 2:
            iso3_to_row[iso3] = row
        if row.get("continent") == "Europe" and len(iso2) == 2:
            europe_iso2.add(iso2)

    europe_iso2 |= EXTRA_EUROPEAN_ISO2
    return iso3_to_row, frozenset(europe_iso2)


def iter_view_election_rows(zip_bytes: bytes) -> csv.DictReader:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        raw = zf.read(VIEW_ELECTION).decode("utf-8-sig")
    return csv.DictReader(io.StringIO(raw))


def ensure_country(
    session: Session,
    cache: dict[str, Country],
    iso2: str,
    country_name: str,
    iso_row: dict[str, Any] | None,
) -> Country:
    region = _slug_region(iso_row.get("region") if iso_row else None)
    if iso2 in cache:
        existing = cache[iso2]
        if existing.name != country_name:
            existing.name = country_name
        if iso_row and existing.region != region:
            existing.region = region
        return existing

    existing = session.get(Country, iso2)
    if existing is None:
        c = Country(
            id=iso2,
            name=country_name,
            region=region,
            flag_emoji=None,
            wikidata_id=None,
        )
        session.add(c)
        cache[iso2] = c
        return c

    cache[iso2] = existing
    if existing.name != country_name:
        existing.name = country_name
    if iso_row and existing.region != region:
        existing.region = region
    return existing


def upsert_election(
    session: Session,
    cache: dict[str, Election],
    *,
    parlgov_election_id: str,
    country_id: str,
    election_date: date,
    election_type: str | None,
    country_name: str,
) -> Election:
    eid = f"pg-e-{parlgov_election_id}"
    if eid in cache:
        return cache[eid]

    status = "complete" if election_date < date.today() else "upcoming"
    etype = _norm_election_type(election_type)

    title_bits = [country_name]
    label = etype.replace("_", " ") if etype else (election_type or "").replace("_", " ")
    if label:
        title_bits.append(label)
    title_bits.append(election_date.isoformat())
    title = " — ".join(title_bits)

    existing = session.get(Election, eid)
    if existing is None:
        obj = Election(
            id=eid,
            country_id=country_id,
            type=etype,
            election_date=election_date,
            status=status,
            title=title,
            description=None,
            wikipedia_url=None,
            wikidata_id=None,
            turnout_pct=None,
            source_url=None,
            last_updated=datetime.now(timezone.utc),
        )
        session.add(obj)
        cache[eid] = obj
        return obj

    existing.country_id = country_id
    existing.type = etype
    existing.election_date = election_date
    existing.status = status
    existing.title = title
    existing.last_updated = datetime.now(timezone.utc)
    cache[eid] = existing
    return existing


def upsert_party(
    session: Session,
    cache: dict[str, Party],
    *,
    parlgov_party_id: str,
    country_id: str,
    party_name: str,
    party_short: str | None,
) -> Party:
    pid = f"pg-p-{parlgov_party_id}"
    if pid in cache:
        return cache[pid]

    existing = session.get(Party, pid)
    if existing is None:
        obj = Party(
            id=pid,
            country_id=country_id,
            name=party_name,
            short_name=party_short,
            color_hex=None,
            wikidata_id=None,
            ideology=None,
        )
        session.add(obj)
        cache[pid] = obj
        return obj

    existing.country_id = country_id
    existing.name = party_name
    existing.short_name = party_short
    cache[pid] = existing
    return existing


def upsert_result(
    session: Session,
    *,
    election_db_id: str,
    party_db_id: str,
    vote_share: float | None,
    seats_won: int | None,
) -> None:
    stmt = select(Result).where(
        Result.election_id == election_db_id,
        Result.party_id == party_db_id,
    )
    existing = session.scalar(stmt)
    if existing is None:
        session.add(
            Result(
                election_id=election_db_id,
                party_id=party_db_id,
                vote_share=vote_share,
                seats_won=seats_won,
                votes_raw=None,
            )
        )
    else:
        existing.vote_share = vote_share
        existing.seats_won = seats_won


def run_ingest(session: Session, zip_bytes: bytes) -> dict[str, int]:
    iso3_to_row, europe_iso2 = load_iso_mappings(zip_bytes)

    country_cache: dict[str, Country] = {}
    election_cache: dict[str, Election] = {}
    party_cache: dict[str, Party] = {}

    stats = {
        "rows_read": 0,
        "rows_imported": 0,
        "rows_skipped": 0,
        "commits": 0,
    }

    pending = 0
    reader = iter_view_election_rows(zip_bytes)
    for raw_row in reader:
        stats["rows_read"] += 1
        row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw_row.items()}

        iso3 = row.get("country_name_short") or ""
        country_name = row.get("country_name") or ""
        iso_row = iso3_to_row.get(iso3)
        iso2 = iso_row.get("iso2") if iso_row else None

        if not iso2 or iso2 not in europe_iso2:
            stats["rows_skipped"] += 1
            continue

        election_date = _parse_date(row.get("election_date"))
        parlgov_election_id = (row.get("election_id") or "").strip()
        parlgov_party_id = (row.get("party_id") or "").strip()
        if not election_date or not parlgov_election_id or not parlgov_party_id:
            stats["rows_skipped"] += 1
            continue

        party_name = row.get("party_name") or row.get("party_name_english") or "Unknown"
        party_short = row.get("party_name_short") or None

        ensure_country(session, country_cache, iso2, country_name or iso2, iso_row)

        election = upsert_election(
            session,
            election_cache,
            parlgov_election_id=parlgov_election_id,
            country_id=iso2,
            election_date=election_date,
            election_type=row.get("election_type"),
            country_name=country_name or iso2,
        )

        party = upsert_party(
            session,
            party_cache,
            parlgov_party_id=parlgov_party_id,
            country_id=iso2,
            party_name=party_name,
            party_short=party_short,
        )

        upsert_result(
            session,
            election_db_id=election.id,
            party_db_id=party.id,
            vote_share=_parse_float(row.get("vote_share")),
            seats_won=_parse_int(row.get("seats")),
        )

        stats["rows_imported"] += 1
        pending += 1
        if pending >= COMMIT_EVERY:
            session.commit()
            stats["commits"] += 1
            pending = 0

    if pending:
        session.commit()
        stats["commits"] += 1

    return stats


def main() -> None:
    session = SessionLocal()
    try:
        with httpx.Client(follow_redirects=True, timeout=120.0) as client:
            zip_bytes = download_parlgov_zip(client)

        stats = run_ingest(session, zip_bytes)
        session.add(
            IngestLog(
                source="parlgov",
                election_id=None,
                status="success",
                message=(
                    f"imported rows={stats['rows_imported']} "
                    f"skipped={stats['rows_skipped']} "
                    f"read={stats['rows_read']} commits={stats['commits']}"
                ),
            )
        )
        session.commit()
        print(stats)
    except Exception as exc:
        session.rollback()
        session.add(
            IngestLog(
                source="parlgov",
                election_id=None,
                status="error",
                message=str(exc)[:2000],
            )
        )
        session.commit()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
