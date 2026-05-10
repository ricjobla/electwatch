"""Parse Wikipedia's 'Elections in YYYY' page as a fallback ingest source.

Returns rows in the same :class:`app.ingest.wikidata.ElectionRow` shape as the
SPARQL path so the upsert logic in :mod:`app.ingest.wikidata` is reused.

Real-page format (e.g. ``Elections_in_2026``):

- the page is organized as bullet lists under continent ``<h2>`` headings;
- each ``<li>`` contains a link to the election article with the title
  starting with the year, e.g. *"2026 Cypriot legislative election"*, and a
  trailing free-text date such as ``", 24 May"`` or ``", 15 March (first
  round) & 22 March (second round)"``;
- the country is **not** a separate cell — it's encoded in the demonym
  (*Cypriot*, *Maltese*, *Czech*, ...) inside the title.

This parser walks every ``<li>`` on the page, extracts the link title plus
the bullet's full text, infers ISO2 from
:data:`app.ingest._europe_iso2.DEMONYM_TO_ISO2` (with a fallback to
:data:`COUNTRY_NAME_TO_ISO2`), and parses the first date that lands in the
requested year. Bullets we can't confidently classify as European are
skipped silently — fewer correct rows beats wrong guesses.

The scraper also handles ``<tr>``-shaped legacy formats (older year pages and
the test fixture) by reusing the same demonym/country lookup over each row's
text.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Iterable

import httpx
from bs4 import BeautifulSoup, Tag

from app.ingest._europe_iso2 import COUNTRY_NAME_TO_ISO2, DEMONYM_TO_ISO2
from app.ingest.wikidata import ElectionRow

WIKIPEDIA_PARSOID_URL = (
    "https://en.wikipedia.org/api/rest_v1/page/html/Elections_in_{year}"
)
WIKIPEDIA_RAW_URL = (
    "https://en.wikipedia.org/w/index.php?title=Elections_in_{year}&action=raw"
)

_MONTHS: dict[str, int] = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

# Match a year followed by a date (most reliable), then DMY / MDY heuristics.
_DATE_DMY_RE = re.compile(
    r"\b(\d{1,2})\s+("
    r"January|February|March|April|May|June|July|August|September|October|November|December"
    r")(?:\s+(\d{4}))?\b",
    re.IGNORECASE,
)
_DATE_MDY_RE = re.compile(
    r"\b("
    r"January|February|March|April|May|June|July|August|September|October|November|December"
    r")\s+(\d{1,2})(?:,\s*(\d{4}))?\b",
    re.IGNORECASE,
)
_DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# Sort lookup keys longest-first so e.g. "North Macedonian" wins over "Macedonian".
_DEMONYMS_SORTED: list[str] = sorted(
    DEMONYM_TO_ISO2.keys(), key=len, reverse=True
)
_COUNTRY_NAMES_SORTED: list[str] = sorted(
    COUNTRY_NAME_TO_ISO2.keys(), key=len, reverse=True
)

# Bigrams that contain a European demonym but refer to non-European places.
# When any of these appear in the row text, drop the row instead of matching
# the bare demonym. Without this, e.g. "British Columbia" (a Canadian
# province) gets tagged GB because of the trailing "British".
_NON_EUROPEAN_PHRASES: tuple[str, ...] = (
    "British Columbia",
    "British Virgin Islands",
    "British Indian Ocean",
    "British Antarctic",
    "French Polynesia",
    "French Guiana",
    "French Southern",
    "Spanish American",  # belt-and-braces; rare on these pages
    "Dutch Caribbean",
    "Dutch Antilles",
    "Portuguese Macau",
    "Portuguese Timor",
    "Russian American",
)


def _all_dates_in_year(text: str, year: int) -> list[date]:
    """All recognized dates in ``text`` that fall in ``year``, in order of appearance."""
    found: list[tuple[int, date]] = []

    for m in _DATE_ISO_RE.finditer(text):
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        if d.year == year:
            found.append((m.start(), d))

    for m in _DATE_DMY_RE.finditer(text):
        day = int(m.group(1))
        month_name = m.group(2).lower()
        target_year = int(m.group(3)) if m.group(3) else year
        if target_year != year:
            continue
        try:
            d = date(year, _MONTHS[month_name], day)
        except (KeyError, ValueError):
            continue
        found.append((m.start(), d))

    for m in _DATE_MDY_RE.finditer(text):
        # Avoid double-counting "24 May" matched by both DMY and MDY.
        # DMY produces text like "24 May"; MDY would not match "24 May" because
        # MDY requires "May 24". Still, guard against weird overlaps by checking
        # the match doesn't share start with an existing one.
        if any(start == m.start() for start, _ in found):
            continue
        month_name = m.group(1).lower()
        day = int(m.group(2))
        target_year = int(m.group(3)) if m.group(3) else year
        if target_year != year:
            continue
        try:
            d = date(year, _MONTHS[month_name], day)
        except (KeyError, ValueError):
            continue
        found.append((m.start(), d))

    found.sort(key=lambda pair: pair[0])
    return [d for _, d in found]


def _parse_first_date_in_year(text: str, year: int) -> date | None:
    dates = _all_dates_in_year(text, year)
    return dates[0] if dates else None


def _iso2_from_text(text: str) -> tuple[str, str] | None:
    """First demonym (longest-match) or country name in ``text`` -> (label, ISO2).

    Returns ``None`` if the text contains a phrase that looks European on
    surface (e.g. "British Columbia") but refers to a non-European place.
    """
    if not text:
        return None
    for blocked in _NON_EUROPEAN_PHRASES:
        if blocked in text:
            return None
    for demonym in _DEMONYMS_SORTED:
        if re.search(r"\b" + re.escape(demonym) + r"\b", text):
            return demonym, DEMONYM_TO_ISO2[demonym]
    for country in _COUNTRY_NAMES_SORTED:
        if re.search(r"\b" + re.escape(country) + r"\b", text):
            return country, COUNTRY_NAME_TO_ISO2[country]
    return None


def _link_url(a: Tag) -> str | None:
    href = a.get("href")
    if not href:
        return None
    if href.startswith("/wiki/"):
        return f"https://en.wikipedia.org{href}"
    if href.startswith("./"):  # Parsoid-relative
        return f"https://en.wikipedia.org/wiki/{href[2:]}"
    if href.startswith("http"):
        return href
    return None


_TITLE_HEAD_RE = re.compile(r"^\s*\d{4}(?:[\u2013-]\d{2,4})?\s+(.+)$")


def _slug_pseudo_qid(country_iso2: str, election_date: date, slug_text: str) -> str:
    """Stable pseudo-id for Wikipedia rows.

    Real Wikidata Q-ids start with ``Q``; the ``wp-`` prefix lets the DB
    primary key (``wikidata-{qid}``) stay globally unique without a schema
    change and makes the row's source obvious by inspection.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", slug_text.lower()).strip("-")[:40] or "election"
    return f"wp-{country_iso2}-{election_date.isoformat()}-{slug}"


def _candidate_blocks(soup: BeautifulSoup) -> Iterable[Tag]:
    """Yield page elements that may contain one election each.

    We yield list items first (current Wikipedia format) and then table rows
    (older / synthetic format used in tests).
    """
    for li in soup.find_all("li"):
        yield li
    for tr in soup.find_all("tr"):
        yield tr


def _extract_row(block: Tag, *, year: int) -> ElectionRow | None:
    a = block.find("a", href=True)
    if not a:
        return None
    title_text = (a.get_text() or "").strip()
    if not title_text:
        return None

    # Require a year prefix so we don't grab arbitrary "See also" links.
    if not re.match(r"^\s*\d{4}\b", title_text):
        return None

    block_text = block.get_text(" ", strip=True)

    # Date may be in the trailing text or, for table rows, in a separate cell.
    eday = _parse_first_date_in_year(block_text, year)
    if eday is None:
        return None

    iso2_match = _iso2_from_text(title_text) or _iso2_from_text(block_text)
    if iso2_match is None:
        return None

    label, iso2 = iso2_match

    # Strip the leading year from the title for the slug.
    head = _TITLE_HEAD_RE.match(title_text)
    slug_source = head.group(1) if head else title_text
    qid = _slug_pseudo_qid(iso2, eday, slug_source)
    wikipedia_url = _link_url(a)

    country_name = label
    return ElectionRow(
        qid=qid,
        title=title_text,
        election_date=eday,
        country_iso2=iso2,
        country_name=country_name,
        country_qid=None,
        election_uri=None,
        wikipedia_url=wikipedia_url,
    )


def parse_elections_html(html: str, *, year: int) -> list[ElectionRow]:
    """Pure parser; takes HTML, returns rows. No network calls."""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[ElectionRow] = []
    seen: set[str] = set()

    for block in _candidate_blocks(soup):
        row = _extract_row(block, year=year)
        if row is None:
            continue
        if row.qid in seen:
            continue
        seen.add(row.qid)
        rows.append(row)

    return rows


def fetch_elections_wikipedia(
    client: httpx.Client,
    *,
    year: int,
) -> list[ElectionRow]:
    """GET the Wikipedia 'Elections in YYYY' page and parse it.

    Tries Parsoid first; on non-200, falls back to the raw MediaWiki source.
    Raises :class:`httpx.HTTPStatusError` if both endpoints fail.
    """
    parsoid_url = WIKIPEDIA_PARSOID_URL.format(year=year)
    resp = client.get(parsoid_url)
    if resp.status_code == 200:
        return parse_elections_html(resp.text, year=year)

    raw_url = WIKIPEDIA_RAW_URL.format(year=year)
    resp = client.get(raw_url)
    resp.raise_for_status()
    return parse_elections_html(resp.text, year=year)
