"""Ingest upcoming/historic European elections from Wikidata (SPARQL)."""

from __future__ import annotations

import time
import urllib.error
from datetime import date, datetime, timezone
from typing import Any, Literal

from SPARQLWrapper import JSON, POST, SPARQLWrapper
from SPARQLWrapper.SPARQLExceptions import EndPointInternalError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.country import Country
from app.models.election import Election
from app.models.ingest_log import IngestLog

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "Electwatch/0.0.0 (https://github.com/ricjobla/electwatch) httpx/0.28.1 [Python/3.13.5]"
# Small pages + per-month queries avoid WDQS gateway HTTP 504 on heavy DISTINCT queries.
PAGE_SIZE = 40
REQUEST_GAP_SECONDS = 1.0
GATEWAY_RETRY_CODES = frozenset({502, 503, 504})
# WDQS HTTP 500 often wraps Blazegraph java.util.concurrent.TimeoutException.
# WDQS sometimes enforces ~1 request/minute; widen paging gap after any HTTP 429.
MIN_GAP_AFTER_429_SECONDS = 61.0


class _RequestSpacing:
    __slots__ = ("gap_seconds",)

    def __init__(self) -> None:
        self.gap_seconds = REQUEST_GAP_SECONDS

    def expand_after_429(self) -> None:
        self.gap_seconds = max(self.gap_seconds, MIN_GAP_AFTER_429_SECONDS)


ELECTIONS_QUERY_TEMPLATE = """
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX bd: <http://www.bigdata.com/rdf#>

SELECT DISTINCT ?election ?electionLabel ?country ?countryLabel ?iso2 ?date WHERE {{
  ?election wdt:P31/wdt:P279* wd:Q40231 .
  ?election wdt:P17 ?country .
  ?country wdt:P30 wd:Q46 .
  ?election wdt:P585 ?date .
  {date_filter}
  OPTIONAL {{ ?country wdt:P297 ?iso2 . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
ORDER BY ?date ?election
LIMIT {limit}
OFFSET {offset}
"""


QueryEchoMode = Literal["never", "first", "all"]


def _emit_query_echo(
    *,
    year: int,
    month: int | None,
    limit: int,
    offset: int,
    query: str,
) -> None:
    m_str = str(month) if month is not None else "—"
    print(
        "\n# Paste into https://query.wikidata.org/\n"
        f"# year={year} month={m_str} LIMIT={limit} OFFSET={offset}\n"
        "# ---\n",
        end="",
        flush=True,
    )
    print(query, flush=True)
    print("# --- end query ---\n", flush=True)


def _date_filter_clause(year: int, month: int | None) -> str:
    """Narrow by calendar month so each WDQS request stays under gateway time limits."""
    if month is None:
        return f"FILTER(YEAR(?date) = {year})"
    return f"FILTER(YEAR(?date) = {year} && MONTH(?date) = {month})"


def _binding_str(binding: dict[str, Any], key: str) -> str | None:
    cell = binding.get(key)
    if not cell:
        return None
    return cell.get("value")


def _qid(uri: str | None) -> str | None:
    if not uri:
        return None
    return uri.rsplit("/", 1)[-1]


def parse_month_list(months_csv: str) -> list[int]:
    """Parse '5,6,7' → [5, 6, 7]; validates 1–12."""
    out: list[int] = []
    for part in months_csv.split(","):
        p = part.strip()
        if not p:
            continue
        m = int(p)
        if m < 1 or m > 12:
            raise ValueError(f"Month must be 1–12, got {m}")
        out.append(m)
    if not out:
        raise ValueError("No months in --months")
    return sorted(set(out))


def quick_sample_months(target_year: int) -> list[int]:
    """
    Few SPARQL rounds for testing: previous month, this month, next month
    when target_year == today's year; otherwise January–March of target_year.
    """
    today = date.today()
    if target_year != today.year:
        return [1, 2, 3]
    prev_m = today.month - 1
    next_m = today.month + 1
    months = {today.month}
    if prev_m >= 1:
        months.add(prev_m)
    if next_m <= 12:
        months.add(next_m)
    return sorted(months)


def _parse_election_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _election_pk(qid: str) -> str:
    return f"wikidata-{qid}"


def ensure_country(
    session: Session,
    cache: dict[str, Country],
    *,
    iso2: str,
    name: str,
    country_wikidata_uri: str | None,
) -> Country | None:
    iso2 = iso2.strip().upper()
    if len(iso2) != 2:
        return None

    wdq = _qid(country_wikidata_uri)

    if iso2 in cache:
        c = cache[iso2]
        if c.name != name:
            c.name = name
        if wdq and not c.wikidata_id:
            c.wikidata_id = wdq
        return c

    existing = session.get(Country, iso2)
    if existing is None:
        c = Country(
            id=iso2,
            name=name,
            region="europe",
            flag_emoji=None,
            wikidata_id=wdq,
        )
        session.add(c)
        cache[iso2] = c
        return c

    cache[iso2] = existing
    if existing.name != name:
        existing.name = name
    if wdq and not existing.wikidata_id:
        existing.wikidata_id = wdq
    return existing


def sparql_client() -> SPARQLWrapper:
    sw = SPARQLWrapper(SPARQL_ENDPOINT, returnFormat=JSON, agent=USER_AGENT)
    sw.setMethod(POST)
    sw.setTimeout(300)
    return sw


def _retry_after_seconds(exc: urllib.error.HTTPError) -> int:
    hdr = exc.headers.get("Retry-After") if exc.headers else None
    if not hdr:
        return 60
    try:
        return max(int(hdr), 1)
    except ValueError:
        return 60


_TRANSIENT_QUERY_ERRORS: tuple[type[Exception], ...] = (
    ConnectionResetError,
    BrokenPipeError,
    TimeoutError,
    urllib.error.URLError,
)


def fetch_election_page(
    sw: SPARQLWrapper,
    spacing: _RequestSpacing,
    *,
    year: int,
    month: int | None,
    limit: int,
    offset: int,
    query_echo: QueryEchoMode = "first",
) -> list[dict[str, Any]]:
    date_filter = _date_filter_clause(year, month)
    query = ELECTIONS_QUERY_TEMPLATE.format(
        date_filter=date_filter,
        limit=limit,
        offset=offset,
    )
    if query_echo == "all" or (query_echo == "first" and offset == 0):
        _emit_query_echo(
            year=year, month=month, limit=limit, offset=offset, query=query
        )
    sw.setQuery(query)
    max_attempts = 12
    for attempt in range(max_attempts):
        try:
            raw = sw.query().convert()
            return list(raw.get("results", {}).get("bindings", []))
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                spacing.expand_after_429()
                wait = max(_retry_after_seconds(exc), 60)
                time.sleep(wait)
                if attempt + 1 == max_attempts:
                    raise RuntimeError(
                        "Wikidata Query Service returned HTTP 429 too many times; "
                        "try again later or widen REQUEST_GAP_SECONDS."
                    ) from exc
            elif exc.code in GATEWAY_RETRY_CODES:
                # 502/503/504: overloaded or query too heavy for one gateway slice.
                wait = min(180, 25 * (2**attempt))
                time.sleep(wait)
                if attempt + 1 == max_attempts:
                    raise RuntimeError(
                        f"Wikidata Query Service HTTP {exc.code} persisted after retries; "
                        "try again later, off-peak, or reduce PAGE_SIZE."
                    ) from exc
            else:
                raise
        except EndPointInternalError as exc:
            # SPARQLWrapper maps HTTP 500 here; body usually contains TimeoutException.
            wait = min(180, 30 * (2**attempt))
            time.sleep(wait)
            if attempt + 1 == max_attempts:
                raise RuntimeError(
                    "Wikidata Query Service returned HTTP 500 (often query timeout); "
                    "retry off-peak, use --months / --quick, or reduce PAGE_SIZE."
                ) from exc
        except _TRANSIENT_QUERY_ERRORS as exc:
            # WDQS often drops long-lived HTTPS connections (connection reset by peer).
            wait = min(120, 10 * (2**attempt))
            time.sleep(wait)
            if attempt + 1 == max_attempts:
                raise RuntimeError(
                    "Wikidata Query Service closed the connection repeatedly; "
                    "retry later or reduce PAGE_SIZE."
                ) from exc


def upsert_election_row(
    session: Session,
    country_cache: dict[str, Country],
    *,
    election_uri: str,
    election_label: str | None,
    country_uri: str | None,
    country_label: str | None,
    iso2: str | None,
    election_day: date,
) -> tuple[str, str]:
    """Returns (election_pk, human title)."""
    eq = _qid(election_uri)
    if not eq:
        raise ValueError("missing election Q-id")

    pk = _election_pk(eq)
    title = election_label or eq
    today = date.today()
    status = "upcoming" if election_day > today else "complete"

    country_id: str | None = None
    if iso2 and country_uri:
        name = country_label or iso2.strip().upper()
        ensured = ensure_country(
            session,
            country_cache,
            iso2=iso2,
            name=name,
            country_wikidata_uri=country_uri,
        )
        if ensured is not None:
            country_id = ensured.id

    wiki_url = f"https://www.wikidata.org/wiki/{eq}"
    now = datetime.now(timezone.utc)

    existing = session.get(Election, pk)
    if existing is None:
        session.add(
            Election(
                id=pk,
                country_id=country_id,
                type=None,
                election_date=election_day,
                status=status,
                title=title,
                description=None,
                wikipedia_url=None,
                wikidata_id=eq,
                turnout_pct=None,
                source_url=wiki_url,
                last_updated=now,
            )
        )
    else:
        existing.country_id = country_id
        existing.election_date = election_day
        existing.status = status
        existing.title = title
        existing.wikidata_id = eq
        existing.source_url = wiki_url
        existing.last_updated = now

    return pk, title


def log_election(session: Session, *, election_id: str | None, status: str, message: str) -> None:
    session.add(
        IngestLog(
            source="wikidata",
            election_id=election_id,
            status=status,
            message=message[:2000],
        )
    )


def run_year(
    session: Session,
    sw: SPARQLWrapper,
    *,
    year: int,
    months: list[int] | None = None,
    query_echo: QueryEchoMode = "first",
) -> dict[str, int]:
    country_cache: dict[str, Country] = {}
    spacing = _RequestSpacing()
    month_list = months if months is not None else list(range(1, 13))
    stats = {
        "pages": 0,
        "rows": 0,
        "upserted": 0,
        "skipped": 0,
        "months_queried": list(month_list),
    }

    first_http_call = True
    for month in month_list:
        offset = 0
        while True:
            if not first_http_call:
                time.sleep(spacing.gap_seconds)
            first_http_call = False

            bindings = fetch_election_page(
                sw,
                spacing,
                year=year,
                month=month,
                limit=PAGE_SIZE,
                offset=offset,
                query_echo=query_echo,
            )
            stats["pages"] += 1

            if not bindings:
                break

            seen_election_uris: set[str] = set()
            for binding in bindings:
                stats["rows"] += 1
                election_uri = _binding_str(binding, "election")
                if not election_uri or election_uri in seen_election_uris:
                    continue
                seen_election_uris.add(election_uri)

                raw_date = _binding_str(binding, "date")
                election_day = _parse_election_date(raw_date)
                if election_day is None:
                    stats["skipped"] += 1
                    log_election(
                        session,
                        election_id=_election_pk(_qid(election_uri) or "unknown"),
                        status="skipped",
                        message=f"unparsed date: {raw_date!r}",
                    )
                    continue

                election_label = _binding_str(binding, "electionLabel")
                country_uri = _binding_str(binding, "country")
                country_label = _binding_str(binding, "countryLabel")
                iso2 = _binding_str(binding, "iso2")

                try:
                    pk, title = upsert_election_row(
                        session,
                        country_cache,
                        election_uri=election_uri,
                        election_label=election_label,
                        country_uri=country_uri,
                        country_label=country_label,
                        iso2=iso2,
                        election_day=election_day,
                    )
                    stats["upserted"] += 1
                    log_election(
                        session,
                        election_id=pk,
                        status="success",
                        message=title,
                    )
                except Exception as exc:
                    stats["skipped"] += 1
                    log_election(
                        session,
                        election_id=_election_pk(_qid(election_uri) or "unknown"),
                        status="error",
                        message=str(exc)[:2000],
                    )

            session.commit()

            if len(bindings) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

    return stats


def main(
    year: int | None = None,
    *,
    months: list[int] | None = None,
    query_echo: QueryEchoMode = "first",
) -> None:
    target_year = year if year is not None else 2026
    session = SessionLocal()
    try:
        sw = sparql_client()
        stats = run_year(
            session,
            sw,
            year=target_year,
            months=months,
            query_echo=query_echo,
        )
        print(stats)
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
        description="Upsert European Wikidata elections for a year (month-scoped SPARQL pages).",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=2026,
        help="Calendar year to fetch (default: 2026)",
    )
    parser.add_argument(
        "--months",
        type=str,
        default=None,
        metavar="M,M",
        help="Comma-separated months (1–12) only, e.g. '5,6' for May & June. Faster test.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help=(
            "Short test run: if --year matches today's year, query previous + current + "
            "next month only; otherwise query January–March of that year."
        ),
    )
    qecho = parser.add_mutually_exclusive_group()
    qecho.add_argument(
        "--no-print-query",
        action="store_true",
        help="Do not print SPARQL to stdout.",
    )
    qecho.add_argument(
        "--print-all-queries",
        action="store_true",
        help="Print SPARQL for every paginated request (verbose).",
    )
    args = parser.parse_args()

    month_filter: list[int] | None = None
    if args.months:
        month_filter = parse_month_list(args.months)
    elif args.quick:
        month_filter = quick_sample_months(args.year)

    echo: QueryEchoMode = "first"
    if args.no_print_query:
        echo = "never"
    elif args.print_all_queries:
        echo = "all"

    main(year=args.year, months=month_filter, query_echo=echo)
