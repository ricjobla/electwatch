"""Ingest upcoming/historic European elections from Wikidata.

Default path: WDQS scoped **per European country** (BIND ?country), then wbgetentities.

Fallback: scan a local `latest-all.json.bz2` (JSON lines) twice — no WDQS election query.

See Wikidata:Tools/For_programmers for dump tooling context.
"""

from __future__ import annotations

import bz2
import gzip
import json
import re
import time
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

import httpx
from SPARQLWrapper import JSON, POST, SPARQLWrapper
from SPARQLWrapper.SPARQLExceptions import EndPointInternalError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.country import Country
from app.models.election import Election
from app.models.ingest_log import IngestLog

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
WIKIBASE_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = "Electwatch/0.0.0 (https://github.com/ricjobla/electwatch) httpx/0.28.1 [Python/3.13.5]"
# WDQS: only election IRI + date (no continent join, labels, or ISO). Details via wbgetentities.
PAGE_SIZE = 40
WIKIBASE_ENTITY_BATCH = 50
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


# Europe (continent) — used only to validate wbgetentities P17 against a cached country set.
EUROPE_QID = "Q46"
ELECTION_CLASS_QID = "Q40231"

EUROPE_COUNTRY_IDS_QUERY = f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?c WHERE {{
  ?c wdt:P30 wd:{EUROPE_QID} .
}}
"""

# Per-country WDQS: fixes ?country so the engine cannot explode over all P17 objects.
ELECTIONS_BY_COUNTRY_QUERY_TEMPLATE = """
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX hint: <http://www.bigdata.com/queryHints#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?election ?date WHERE {{
  BIND(wd:{country_qid} AS ?country) .
  hint:Query hint:optimizer "None" .
  ?election wdt:P17 ?country .
  ?election wdt:P585 ?date . hint:Prior hint:rangeSafe true .
  {date_filter}
  wd:""" + ELECTION_CLASS_QID + """ ^wdt:P279*/^wdt:P31 ?election .
}}
ORDER BY ?date ?election
LIMIT {limit}
OFFSET {offset}
"""

ELECTION_TYPES_QUERY = f"""
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?t WHERE {{
  {{ BIND(wd:{ELECTION_CLASS_QID} AS ?t) }}
  UNION
  {{ ?t wdt:P279+ wd:{ELECTION_CLASS_QID} . }}
}}
"""

_QID_RE = re.compile(r"^Q[1-9]\d*$")


def _validate_qid(qid: str) -> str:
    if not _QID_RE.match(qid):
        raise ValueError(f"invalid Wikidata Q-id: {qid!r}")
    return qid


QueryEchoMode = Literal["never", "first", "all"]


def _emit_query_echo(
    *,
    country_qid: str | None,
    year: int,
    month: int | None,
    limit: int,
    offset: int,
    query: str,
) -> None:
    m_str = str(month) if month is not None else "—"
    c_str = country_qid if country_qid is not None else "—"
    print(
        "\n# Paste into https://query.wikidata.org/\n"
        f"# country={c_str} year={year} month={m_str} LIMIT={limit} OFFSET={offset}\n"
        "# ---\n",
        end="",
        flush=True,
    )
    print(query, flush=True)
    print("# --- end query ---\n", flush=True)


def _date_filter_clause(year: int, month: int | None) -> str:
    """
    Narrow by calendar month using xsd:dateTime bounds (WDQS range scans).
    Prefer this over FILTER(YEAR/MONTH(?date)) — see Wikidata query optimization.
    """
    if month is None:
        lo = f'"{year}-01-01T00:00:00"^^xsd:dateTime'
        hi = f'"{year + 1}-01-01T00:00:00"^^xsd:dateTime'
        return f"FILTER({lo} <= ?date && ?date < {hi})"
    lo = f'"{year}-{month:02d}-01T00:00:00"^^xsd:dateTime'
    hi_exclusive = _next_datetime_literal_after_month(year, month)
    return f"FILTER({lo} <= ?date && ?date < {hi_exclusive})"


def _next_datetime_literal_after_month(year: int, month: int) -> str:
    """First instant after the last calendar day of (year, month), as xsd:dateTime."""
    if month == 12:
        return f'"{year + 1}-01-01T00:00:00"^^xsd:dateTime'
    return f'"{year}-{month + 1:02d}-01T00:00:00"^^xsd:dateTime'


def _binding_str(binding: dict[str, Any], key: str) -> str | None:
    cell = binding.get(key)
    if not cell:
        return None
    return cell.get("value")


def _qid(uri: str | None) -> str | None:
    if not uri:
        return None
    return uri.rsplit("/", 1)[-1]


def _wikidata_entity_uri(qid: str) -> str:
    return f"http://www.wikidata.org/entity/{qid}"


def _entity_en_label(entity: dict[str, Any]) -> str | None:
    labels = entity.get("labels") or {}
    en = labels.get("en")
    if isinstance(en, dict):
        v = en.get("value")
        if isinstance(v, str) and v.strip():
            return v.strip()
    for _lang, cell in labels.items():
        if isinstance(cell, dict):
            v = cell.get("value")
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def _claim_first_item_id(claims: dict[str, Any], prop: str) -> str | None:
    stmts = claims.get(prop)
    if not isinstance(stmts, list):
        return None
    for st in stmts:
        mainsnak = st.get("mainsnak", {})
        if mainsnak.get("snaktype") != "value":
            continue
        dv = mainsnak.get("datavalue", {})
        if dv.get("type") == "wikibase-entityid":
            vid = dv.get("value", {}).get("id")
            if isinstance(vid, str):
                return vid
    return None


def _claim_first_string(claims: dict[str, Any], prop: str) -> str | None:
    stmts = claims.get(prop)
    if not isinstance(stmts, list):
        return None
    for st in stmts:
        mainsnak = st.get("mainsnak", {})
        if mainsnak.get("snaktype") != "value":
            continue
        dv = mainsnak.get("datavalue", {})
        if dv.get("type") == "string":
            v = dv.get("value")
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def _wikidata_time_to_date(time_str: str | None) -> date | None:
    if not time_str or not isinstance(time_str, str) or not time_str.startswith("+"):
        return None
    body = time_str[1:]
    day = body.split("T", 1)[0] if "T" in body else body[:10]
    try:
        return date.fromisoformat(day)
    except ValueError:
        return None


def _claim_first_time_date(claims: dict[str, Any], prop: str) -> date | None:
    stmts = claims.get(prop)
    if not isinstance(stmts, list):
        return None
    for st in stmts:
        mainsnak = st.get("mainsnak", {})
        if mainsnak.get("snaktype") != "value":
            continue
        dv = mainsnak.get("datavalue", {})
        if dv.get("type") == "time":
            return _wikidata_time_to_date(dv.get("value", {}).get("time"))
    return None


def _entity_has_p31_in(claims: dict[str, Any], allowed: frozenset[str]) -> bool:
    stmts = claims.get("P31")
    if not isinstance(stmts, list):
        return False
    for st in stmts:
        mainsnak = st.get("mainsnak", {})
        if mainsnak.get("snaktype") != "value":
            continue
        dv = mainsnak.get("datavalue", {})
        if dv.get("type") == "wikibase-entityid":
            vid = dv.get("value", {}).get("id")
            if isinstance(vid, str) and vid in allowed:
                return True
    return False


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

_TRANSIENT_HTTP_ERRORS: tuple[type[Exception], ...] = (
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.RemoteProtocolError,
    httpx.TimeoutException,
)


def _retry_after_from_headers(headers: httpx.Headers) -> int:
    hdr = headers.get("retry-after")
    if not hdr:
        return 60
    try:
        return max(int(hdr), 1)
    except ValueError:
        return 60


def _sparql_select_bindings(
    sw: SPARQLWrapper,
    spacing: _RequestSpacing,
    *,
    query: str,
) -> list[dict[str, Any]]:
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
            wait = min(180, 30 * (2**attempt))
            time.sleep(wait)
            if attempt + 1 == max_attempts:
                raise RuntimeError(
                    "Wikidata Query Service returned HTTP 500 (often query timeout); "
                    "retry off-peak, use --months / --quick, or reduce PAGE_SIZE."
                ) from exc
        except _TRANSIENT_QUERY_ERRORS as exc:
            wait = min(120, 10 * (2**attempt))
            time.sleep(wait)
            if attempt + 1 == max_attempts:
                raise RuntimeError(
                    "Wikidata Query Service closed the connection repeatedly; "
                    "retry later or reduce PAGE_SIZE."
                ) from exc


def fetch_europe_country_qids(sw: SPARQLWrapper, spacing: _RequestSpacing) -> frozenset[str]:
    """Items with P30 = Europe; used to filter election country (P17) without a WDQS join."""
    rows = _sparql_select_bindings(sw, spacing, query=EUROPE_COUNTRY_IDS_QUERY)
    out: set[str] = set()
    for b in rows:
        q = _qid(_binding_str(b, "c"))
        if q:
            out.add(q)
    return frozenset(out)


def fetch_election_type_qids(sw: SPARQLWrapper, spacing: _RequestSpacing) -> frozenset[str]:
    """Q40231 plus subclasses (P279+) for dump filtering."""
    try:
        rows = _sparql_select_bindings(sw, spacing, query=ELECTION_TYPES_QUERY)
        out: set[str] = {ELECTION_CLASS_QID}
        for b in rows:
            q = _qid(_binding_str(b, "t"))
            if q:
                out.add(q)
        return frozenset(out)
    except RuntimeError:
        print(
            "wikidata ingest: election taxonomy SPARQL failed; "
            f"using only P31={ELECTION_CLASS_QID} for dump filtering.",
            flush=True,
        )
        return frozenset({ELECTION_CLASS_QID})


def _open_dump_text(path: Path):
    suf = "".join(path.suffixes).lower()
    if suf.endswith(".bz2"):
        return bz2.open(path, "rt", encoding="utf-8")
    if suf.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def iter_wikidata_json_entities(path: Path) -> Iterator[dict[str, Any]]:
    """Stream a Wikidata JSON dump (newline-delimited JSON objects, one item per line)."""
    with _open_dump_text(path) as fh:
        for line in fh:
            raw = line.strip()
            if not raw or raw in ("[", "{"):
                continue
            if raw in ("]", "}"):
                continue
            if raw.endswith(","):
                raw = raw[:-1].strip()
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and obj.get("type") == "item":
                yield obj


def _date_in_ingest_scope(election_day: date, year: int, months: list[int]) -> bool:
    if election_day.year != year:
        return False
    return election_day.month in months


def _wikibase_json_get(
    client: httpx.Client,
    spacing: _RequestSpacing,
    *,
    params: dict[str, str],
) -> dict[str, Any]:
    max_attempts = 12
    for attempt in range(max_attempts):
        try:
            r = client.get(WIKIBASE_API, params=params)
            if r.status_code == 429:
                spacing.expand_after_429()
                wait = max(_retry_after_from_headers(r.headers), 60)
                time.sleep(wait)
                if attempt + 1 == max_attempts:
                    raise RuntimeError(
                        "wikidata.org wbgetentities returned HTTP 429 too many times; "
                        "try again later."
                    )
                continue
            if r.status_code in GATEWAY_RETRY_CODES:
                time.sleep(min(180, 25 * (2**attempt)))
                if attempt + 1 == max_attempts:
                    raise RuntimeError(
                        f"wikidata.org API HTTP {r.status_code} persisted after retries."
                    )
                continue
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, dict):
                raise RuntimeError("wikidata.org API returned non-object JSON")
            return data
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code if exc.response is not None else 0
            if code in GATEWAY_RETRY_CODES:
                time.sleep(min(180, 25 * (2**attempt)))
                if attempt + 1 == max_attempts:
                    raise RuntimeError(
                        f"wikidata.org API HTTP {code} persisted after retries."
                    ) from exc
                continue
            raise
        except _TRANSIENT_HTTP_ERRORS as exc:
            time.sleep(min(120, 10 * (2**attempt)))
            if attempt + 1 == max_attempts:
                raise RuntimeError(
                    "wikidata.org API closed the connection repeatedly; retry later."
                ) from exc


def wbgetentities_map(
    client: httpx.Client,
    spacing: _RequestSpacing,
    qids: list[str],
) -> dict[str, dict[str, Any]]:
    """Fetch entities via Wikibase Action API (wbgetentities); max 50 ids per request."""
    uniq = sorted({q for q in qids if q})
    out: dict[str, dict[str, Any]] = {}
    for i in range(0, len(uniq), WIKIBASE_ENTITY_BATCH):
        batch = uniq[i : i + WIKIBASE_ENTITY_BATCH]
        params = {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(batch),
            "props": "labels|claims",
            "languages": "en",
        }
        payload = _wikibase_json_get(client, spacing, params=params)
        entities = payload.get("entities")
        if not isinstance(entities, dict):
            continue
        for qid, ent in entities.items():
            if not isinstance(ent, dict):
                continue
            if "missing" in ent:
                continue
            out[qid] = ent
    return out


def fetch_election_page_for_country(
    sw: SPARQLWrapper,
    spacing: _RequestSpacing,
    *,
    country_qid: str,
    year: int,
    month: int | None,
    limit: int,
    offset: int,
    emit_echo: bool,
) -> list[dict[str, Any]]:
    cq = _validate_qid(country_qid)
    date_filter = _date_filter_clause(year, month)
    query = ELECTIONS_BY_COUNTRY_QUERY_TEMPLATE.format(
        country_qid=cq,
        date_filter=date_filter,
        limit=limit,
        offset=offset,
    )
    if emit_echo:
        _emit_query_echo(
            country_qid=cq,
            year=year,
            month=month,
            limit=limit,
            offset=offset,
            query=query,
        )
    return _sparql_select_bindings(sw, spacing, query=query)


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


def run_year_from_dump(
    session: Session,
    dump_path: Path,
    sw: SPARQLWrapper,
    *,
    year: int,
    months: list[int] | None = None,
) -> dict[str, Any]:
    """Two-pass scan of a local Wikidata JSON dump (no per-election WDQS)."""
    country_cache: dict[str, Country] = {}
    spacing = _RequestSpacing()
    month_list = months if months is not None else list(range(1, 13))
    stats: dict[str, Any] = {
        "mode": "dump",
        "dump_entities_seen": 0,
        "candidates": 0,
        "upserted": 0,
        "skipped": 0,
        "months_filter": list(month_list),
    }

    europe_qids = fetch_europe_country_qids(sw, spacing)
    if len(europe_qids) < 20:
        raise RuntimeError(
            "Europe country lookup returned too few Wikidata ids; aborting to avoid "
            "misclassifying elections."
        )
    election_types = fetch_election_type_qids(sw, spacing)
    time.sleep(spacing.gap_seconds)

    candidates: dict[str, tuple[str, date, str | None]] = {}
    needed_countries: set[str] = set()

    for ent in iter_wikidata_json_entities(dump_path):
        stats["dump_entities_seen"] += 1
        qid = ent.get("id")
        if not isinstance(qid, str) or not qid.startswith("Q"):
            continue
        claims = ent.get("claims") or {}
        if not _entity_has_p31_in(claims, election_types):
            continue
        country_id = _claim_first_item_id(claims, "P17")
        if not country_id or country_id not in europe_qids:
            continue
        eday = _claim_first_time_date(claims, "P585")
        if eday is None or not _date_in_ingest_scope(eday, year, month_list):
            continue
        title = _entity_en_label(ent)
        candidates[qid] = (country_id, eday, title)
        needed_countries.add(country_id)

    stats["candidates"] = len(candidates)

    country_iso: dict[str, str | None] = {}
    country_labels: dict[str, str | None] = {}
    for ent in iter_wikidata_json_entities(dump_path):
        qid = ent.get("id")
        if not isinstance(qid, str) or qid not in needed_countries:
            continue
        claims = ent.get("claims") or {}
        country_iso[qid] = _claim_first_string(claims, "P297")
        country_labels[qid] = _entity_en_label(ent)

    for eq, (country_id, election_day, election_label) in candidates.items():
        iso2 = country_iso.get(country_id)
        country_label = country_labels.get(country_id)
        country_uri = _wikidata_entity_uri(country_id)
        election_uri = _wikidata_entity_uri(eq)
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
            log_election(session, election_id=pk, status="success", message=title)
        except Exception as exc:
            stats["skipped"] += 1
            log_election(
                session,
                election_id=_election_pk(eq),
                status="error",
                message=str(exc)[:2000],
            )

    session.commit()
    return stats


def run_year(
    session: Session,
    sw: SPARQLWrapper,
    http: httpx.Client,
    *,
    year: int,
    months: list[int] | None = None,
    query_echo: QueryEchoMode = "first",
) -> dict[str, Any]:
    country_cache: dict[str, Country] = {}
    spacing = _RequestSpacing()
    month_list = months if months is not None else list(range(1, 13))
    stats: dict[str, Any] = {
        "mode": "sparql_by_country",
        "pages": 0,
        "rows": 0,
        "upserted": 0,
        "skipped": 0,
        "months_queried": list(month_list),
    }

    europe_qids = fetch_europe_country_qids(sw, spacing)
    if len(europe_qids) < 20:
        raise RuntimeError(
            "Europe country lookup returned too few Wikidata ids; aborting to avoid "
            "misclassifying elections."
        )
    countries_ent_by_qid = wbgetentities_map(http, spacing, sorted(europe_qids))
    time.sleep(spacing.gap_seconds)

    europe_sorted = sorted(europe_qids)
    first_month = month_list[0]
    first_country = europe_sorted[0]
    n_months = len(month_list)
    n_countries = len(europe_sorted)
    print(
        f"wikidata ingest: SPARQL by country — year={year}, "
        f"{n_months} month(s), {n_countries} European country/territory Q-ids",
        flush=True,
    )

    first_http_call = True
    for mi, month in enumerate(month_list, start=1):
        for ci, country_qid in enumerate(europe_sorted, start=1):
            cq = _validate_qid(country_qid)
            cent0 = countries_ent_by_qid.get(cq)
            country_label0 = _entity_en_label(cent0) if cent0 else None
            country_bit = f"{cq} ({country_label0})" if country_label0 else cq
            offset = 0
            page_idx = 0
            while True:
                if not first_http_call:
                    time.sleep(spacing.gap_seconds)
                first_http_call = False

                emit_echo = query_echo == "all" or (
                    query_echo == "first"
                    and offset == 0
                    and month == first_month
                    and country_qid == first_country
                )

                page_idx += 1
                print(
                    f"wikidata ingest: … month {mi}/{n_months} (month={month}) · "
                    f"country {ci}/{n_countries} · {country_bit} · "
                    f"page {page_idx} offset={offset}",
                    flush=True,
                )

                bindings = fetch_election_page_for_country(
                    sw,
                    spacing,
                    country_qid=cq,
                    year=year,
                    month=month,
                    limit=PAGE_SIZE,
                    offset=offset,
                    emit_echo=emit_echo,
                )
                stats["pages"] += 1

                n_bind = len(bindings)
                print(
                    f"wikidata ingest:   WDQS returned {n_bind} binding(s)",
                    flush=True,
                )

                if not bindings:
                    break

                page_rows: list[tuple[str, str | None]] = []
                seen_election_uris: set[str] = set()
                for binding in bindings:
                    stats["rows"] += 1
                    election_uri = _binding_str(binding, "election")
                    if not election_uri or election_uri in seen_election_uris:
                        continue
                    seen_election_uris.add(election_uri)
                    page_rows.append((election_uri, _binding_str(binding, "date")))

                election_qids = [q for u, _ in page_rows if (q := _qid(u))]
                elections_ent = wbgetentities_map(http, spacing, election_qids)

                for election_uri, raw_date in page_rows:
                    eq = _qid(election_uri)
                    if not eq:
                        stats["skipped"] += 1
                        continue

                    ent = elections_ent.get(eq)
                    if not ent:
                        stats["skipped"] += 1
                        log_election(
                            session,
                            election_id=_election_pk(eq),
                            status="skipped",
                            message="election entity missing from wbgetentities",
                        )
                        continue

                    claims = ent.get("claims") or {}
                    election_day = _claim_first_time_date(claims, "P585") or _parse_election_date(
                        raw_date
                    )
                    if election_day is None:
                        stats["skipped"] += 1
                        log_election(
                            session,
                            election_id=_election_pk(eq),
                            status="skipped",
                            message=f"unparsed election date (claims/P585 and SPARQL): {raw_date!r}",
                        )
                        continue

                    country_qid_claim = _claim_first_item_id(claims, "P17")
                    if not country_qid_claim:
                        stats["skipped"] += 1
                        log_election(
                            session,
                            election_id=_election_pk(eq),
                            status="skipped",
                            message="no country statement (P17) on election item",
                        )
                        continue

                    if country_qid_claim != cq:
                        stats["skipped"] += 1
                        log_election(
                            session,
                            election_id=_election_pk(eq),
                            status="skipped",
                            message=(
                                f"P17={country_qid_claim} does not match scoped country {cq}"
                            ),
                        )
                        continue

                    cent = countries_ent_by_qid.get(country_qid_claim)
                    iso2 = (
                        _claim_first_string(cent.get("claims") or {}, "P297") if cent else None
                    )
                    election_label = _entity_en_label(ent)
                    country_label = _entity_en_label(cent) if cent else None
                    country_uri = _wikidata_entity_uri(country_qid_claim)

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
                            election_id=_election_pk(eq),
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
    dump_path: Path | None = None,
) -> None:
    target_year = year if year is not None else 2026
    session = SessionLocal()
    try:
        sw = sparql_client()
        if dump_path is not None:
            stats = run_year_from_dump(
                session,
                dump_path,
                sw,
                year=target_year,
                months=months,
            )
        else:
            with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=120.0) as http:
                stats = run_year(
                    session,
                    sw,
                    http,
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
        description=(
            "Upsert European Wikidata elections: WDQS per-country × month paging plus "
            "wbgetentities, or --dump for local JSON dump scanning."
        ),
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
    parser.add_argument(
        "--dump",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "Local Wikidata JSON dump (e.g. latest-all.json.bz2). Two-pass scan; only "
            "light WDQS for Europe + election-type ids. Ignores --print-* query flags."
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

    if args.dump is not None and not args.dump.is_file():
        parser.error(f"--dump not a file: {args.dump}")

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

    main(year=args.year, months=month_filter, query_echo=echo, dump_path=args.dump)
