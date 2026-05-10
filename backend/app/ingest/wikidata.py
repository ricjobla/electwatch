"""Ingest upcoming European elections from Wikidata.

Strategy: a single optimized SPARQL query against WDQS, with a Wikipedia
"Elections in YYYY" fallback for resilience. Replaces the previous per-country
× per-month pagination, which fanned out into 600+ requests and stalled on
WDQS rate limits.

The SPARQL query narrows to European countries via ``?country wdt:P30 wd:Q46 ;
wdt:P297 ?iso2`` *before* the election join, so the planner only ever touches
~45 country items. Date is constrained by a half-open ``xsd:dateTime`` range
with ``hint:rangeSafe`` so Blazegraph can use a range scan rather than a
``YEAR()``/``MONTH()`` filter on every binding.

ParlGov continues to own historic European results
(:mod:`app.ingest.parlgov`); this module only handles upcoming/calendar data.

CLI::

    python -m app.ingest.wikidata --year 2026
    python -m app.ingest.wikidata --year 2026 --source wikipedia
    python -m app.ingest.wikidata --year 2026 --dry-run --months 5,6
"""

from __future__ import annotations

import time
import urllib.error
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Literal

import httpx
from SPARQLWrapper import JSON, POST, SPARQLWrapper
from SPARQLWrapper.SPARQLExceptions import (
    EndPointInternalError,
    SPARQLWrapperException,
)
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.country import Country
from app.models.election import Election
from app.models.ingest_log import IngestLog

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = (
    "Electwatch/0.1.0 "
    "(https://github.com/ricjobla/electwatch; electwatch@example.com) "
    "httpx/0.28"
)
SPARQL_TIMEOUT_SECONDS = 30
WIKIPEDIA_HTTP_TIMEOUT = 20.0

SourceMode = Literal["auto", "sparql", "wikipedia"]


@dataclass(frozen=True)
class ElectionRow:
    """Normalized shape produced by both the SPARQL and Wikipedia paths.

    `qid` is a Wikidata Q-id (``Q...``) for SPARQL rows or a deterministic
    pseudo-id (``wp-...``) for Wikipedia rows. The DB ``Election.id`` derives
    from this via :func:`_election_pk`.
    """

    qid: str
    title: str
    election_date: date
    country_iso2: str
    country_name: str
    country_qid: str | None = None
    election_uri: str | None = None
    wikipedia_url: str | None = None


SPARQL_QUERY_TEMPLATE = """\
PREFIX wd:   <http://www.wikidata.org/entity/>
PREFIX wdt:  <http://www.wikidata.org/prop/direct/>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
PREFIX hint: <http://www.bigdata.com/queryHints#>

SELECT ?election ?electionLabel ?country ?countryLabel ?iso2 ?date WHERE {{
  ?country  wdt:P30  wd:Q46 ;
            wdt:P297 ?iso2 .

  ?election wdt:P17  ?country ;
            wdt:P585 ?date ;
            wdt:P31  ?type .
  ?type     wdt:P279* wd:Q40231 .

  hint:Prior hint:rangeSafe true .
  FILTER("{date_from}T00:00:00"^^xsd:dateTime <= ?date
      && ?date < "{date_to}T00:00:00"^^xsd:dateTime)

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
ORDER BY ?date
"""


def build_sparql_query(*, date_from: date, date_to: date) -> str:
    """Return the SPARQL text for a half-open ``[date_from, date_to)`` window."""
    return SPARQL_QUERY_TEMPLATE.format(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
    )


def sparql_client() -> SPARQLWrapper:
    sw = SPARQLWrapper(SPARQL_ENDPOINT, returnFormat=JSON, agent=USER_AGENT)
    sw.setMethod(POST)
    sw.setTimeout(SPARQL_TIMEOUT_SECONDS)
    return sw


def _qid(uri: str | None) -> str | None:
    if not uri:
        return None
    return uri.rsplit("/", 1)[-1]


def _binding_str(binding: dict[str, Any], key: str) -> str | None:
    cell = binding.get(key)
    if not cell:
        return None
    return cell.get("value")


def _parse_election_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _rows_from_bindings(bindings: list[dict[str, Any]]) -> list[ElectionRow]:
    out: list[ElectionRow] = []
    seen: set[str] = set()
    for b in bindings:
        election_uri = _binding_str(b, "election")
        eq = _qid(election_uri)
        if not eq or eq in seen:
            continue
        eday = _parse_election_date(_binding_str(b, "date"))
        if eday is None:
            continue
        iso2 = (_binding_str(b, "iso2") or "").upper()
        if len(iso2) != 2:
            continue
        seen.add(eq)
        out.append(
            ElectionRow(
                qid=eq,
                title=_binding_str(b, "electionLabel") or eq,
                election_date=eday,
                country_iso2=iso2,
                country_name=_binding_str(b, "countryLabel") or iso2,
                country_qid=_qid(_binding_str(b, "country")),
                election_uri=election_uri,
            )
        )
    return out


def fetch_elections_sparql(
    sw: SPARQLWrapper,
    *,
    date_from: date,
    date_to: date,
) -> list[ElectionRow]:
    """Run the single SPARQL round-trip and return parsed rows.

    Raises on any transport/server failure; callers (notably
    :func:`run_year`) decide whether to fall back to Wikipedia.
    """
    sw.setQuery(build_sparql_query(date_from=date_from, date_to=date_to))
    raw = sw.query().convert()
    bindings = list(raw.get("results", {}).get("bindings", []))
    return _rows_from_bindings(bindings)


def _election_pk(qid: str) -> str:
    return f"wikidata-{qid}"


def ensure_country(
    session: Session,
    cache: dict[str, Country],
    *,
    iso2: str,
    name: str,
    country_qid: str | None,
) -> Country | None:
    iso2 = iso2.strip().upper()
    if len(iso2) != 2:
        return None

    if iso2 in cache:
        c = cache[iso2]
        if c.name != name:
            c.name = name
        if country_qid and not c.wikidata_id:
            c.wikidata_id = country_qid
        return c

    existing = session.get(Country, iso2)
    if existing is None:
        c = Country(
            id=iso2,
            name=name,
            region="europe",
            flag_emoji=None,
            wikidata_id=country_qid,
        )
        session.add(c)
        cache[iso2] = c
        return c

    cache[iso2] = existing
    if existing.name != name:
        existing.name = name
    if country_qid and not existing.wikidata_id:
        existing.wikidata_id = country_qid
    return existing


def upsert_election_row(
    session: Session,
    country_cache: dict[str, Country],
    row: ElectionRow,
) -> tuple[str, str]:
    """Upsert a single :class:`ElectionRow`; returns ``(election_pk, title)``."""
    pk = _election_pk(row.qid)
    today = date.today()
    status = "upcoming" if row.election_date > today else "complete"

    ensured = ensure_country(
        session,
        country_cache,
        iso2=row.country_iso2,
        name=row.country_name,
        country_qid=row.country_qid,
    )
    country_id = ensured.id if ensured else None

    source_url = row.wikipedia_url or f"https://www.wikidata.org/wiki/{row.qid}"
    now = datetime.now(timezone.utc)

    existing = session.get(Election, pk)
    if existing is None:
        session.add(
            Election(
                id=pk,
                country_id=country_id,
                type=None,
                election_date=row.election_date,
                status=status,
                title=row.title,
                description=None,
                wikipedia_url=row.wikipedia_url,
                wikidata_id=row.qid,
                turnout_pct=None,
                source_url=source_url,
                last_updated=now,
            )
        )
    else:
        if country_id is not None:
            existing.country_id = country_id
        existing.election_date = row.election_date
        existing.status = status
        existing.title = row.title
        existing.wikidata_id = row.qid
        if row.wikipedia_url and not existing.wikipedia_url:
            existing.wikipedia_url = row.wikipedia_url
        existing.source_url = source_url
        existing.last_updated = now

    return pk, row.title


def log_election(
    session: Session,
    *,
    election_id: str | None,
    status: str,
    message: str,
) -> None:
    session.add(
        IngestLog(
            source="wikidata",
            election_id=election_id,
            status=status,
            message=message[:2000],
        )
    )


# Errors that should trigger the Wikipedia fallback when source="auto".
# Bare bugs in our code (TypeError, AttributeError, ...) intentionally do not.
_SPARQL_TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    EndPointInternalError,
    SPARQLWrapperException,
    urllib.error.HTTPError,
    urllib.error.URLError,
    TimeoutError,
    ConnectionError,
    OSError,
)


def parse_month_list(months_csv: str) -> list[int]:
    """Parse ``"5,6,7"`` -> ``[5, 6, 7]``; rejects values outside 1..12."""
    out: list[int] = []
    for part in months_csv.split(","):
        p = part.strip()
        if not p:
            continue
        m = int(p)
        if not 1 <= m <= 12:
            raise ValueError(f"Month must be 1-12, got {m}")
        out.append(m)
    if not out:
        raise ValueError("No months in --months")
    return sorted(set(out))


def _print_dry_run(rows: list[ElectionRow]) -> None:
    header = f"{'date':<12} {'iso2':<5} {'qid':<28}  title"
    print(header, flush=True)
    print("-" * len(header), flush=True)
    for r in rows:
        print(
            f"{r.election_date.isoformat():<12} "
            f"{r.country_iso2:<5} "
            f"{r.qid:<28}  "
            f"{r.title}",
            flush=True,
        )


def run_year(
    session: Session,
    *,
    year: int,
    source: SourceMode = "auto",
    months: list[int] | None = None,
    dry_run: bool = False,
    sparql: SPARQLWrapper | None = None,
    http: httpx.Client | None = None,
) -> dict[str, Any]:
    """Single-query SPARQL ingest with optional Wikipedia fallback.

    - ``source="auto"`` (default): try SPARQL first; on transient transport
      errors, fall back to the Wikipedia "Elections in YYYY" parser.
    - ``source="sparql"``: SPARQL only; raise on failure.
    - ``source="wikipedia"``: skip SPARQL; use the Wikipedia parser directly.

    ``sparql`` and ``http`` are injection points for tests; production callers
    can leave both None and we'll construct fresh clients.
    """
    date_from = date(year, 1, 1)
    date_to = date(year + 1, 1, 1)

    rows: list[ElectionRow] = []
    used_source = ""
    sparql_error: str | None = None

    if source in ("auto", "sparql"):
        sw = sparql or sparql_client()
        t0 = time.perf_counter()
        try:
            rows = fetch_elections_sparql(sw, date_from=date_from, date_to=date_to)
            used_source = "sparql"
            print(
                f"wikidata ingest: SPARQL returned {len(rows)} row(s) "
                f"in {time.perf_counter() - t0:.2f}s",
                flush=True,
            )
        except _SPARQL_TRANSIENT_ERRORS as exc:
            if source == "sparql":
                raise
            sparql_error = f"{type(exc).__name__}: {exc}"
            print(
                f"wikidata ingest: SPARQL failed ({sparql_error}); "
                "falling back to Wikipedia.",
                flush=True,
            )
            rows = []

    if source == "wikipedia" or (source == "auto" and not rows):
        # Lazy import to avoid a circular dep with wikipedia_calendar.
        from app.ingest.wikipedia_calendar import fetch_elections_wikipedia

        t0 = time.perf_counter()
        if http is None:
            with httpx.Client(
                headers={"User-Agent": USER_AGENT},
                timeout=WIKIPEDIA_HTTP_TIMEOUT,
                follow_redirects=True,
            ) as client:
                rows = fetch_elections_wikipedia(client, year=year)
        else:
            rows = fetch_elections_wikipedia(http, year=year)
        used_source = "wikipedia"
        print(
            f"wikidata ingest: Wikipedia returned {len(rows)} row(s) "
            f"in {time.perf_counter() - t0:.2f}s",
            flush=True,
        )

    if months:
        rows = [r for r in rows if r.election_date.month in months]

    stats: dict[str, Any] = {
        "source": used_source,
        "year": year,
        "months_filter": list(months) if months else None,
        "rows_fetched": len(rows),
        "upserted": 0,
        "skipped": 0,
        "dry_run": dry_run,
        "sparql_error": sparql_error,
    }

    if dry_run:
        _print_dry_run(rows)
        return stats

    country_cache: dict[str, Country] = {}
    for row in rows:
        try:
            pk, title = upsert_election_row(session, country_cache, row)
            stats["upserted"] += 1
            log_election(session, election_id=pk, status="success", message=title)
        except Exception as exc:
            stats["skipped"] += 1
            log_election(
                session,
                election_id=_election_pk(row.qid),
                status="error",
                message=str(exc),
            )

    session.commit()
    return stats


def main(
    *,
    year: int,
    source: SourceMode = "auto",
    months: list[int] | None = None,
    dry_run: bool = False,
) -> None:
    session = SessionLocal()
    try:
        stats = run_year(
            session,
            year=year,
            source=source,
            months=months,
            dry_run=dry_run,
        )
        print(stats, flush=True)
    except Exception as exc:
        session.rollback()
        session.add(
            IngestLog(
                source="wikidata",
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
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Upsert upcoming European elections from Wikidata (single SPARQL) "
            "with a Wikipedia 'Elections in YYYY' fallback."
        ),
    )
    parser.add_argument(
        "--year",
        type=int,
        default=date.today().year,
        help="Calendar year to ingest (default: current year).",
    )
    parser.add_argument(
        "--source",
        choices=["auto", "sparql", "wikipedia"],
        default="auto",
        help="auto = try SPARQL, fall back to Wikipedia on transport errors.",
    )
    parser.add_argument(
        "--months",
        type=str,
        default=None,
        metavar="M,M",
        help="Comma-separated months (1-12) to keep, e.g. '5,6' for May & June.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print rows that would be upserted; do not write to the DB.",
    )
    args = parser.parse_args()

    month_filter = parse_month_list(args.months) if args.months else None
    main(
        year=args.year,
        source=args.source,
        months=month_filter,
        dry_run=args.dry_run,
    )
