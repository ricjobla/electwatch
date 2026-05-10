"""Live network tests, opt-in via ``pytest -m live``.

These tests exist to catch upstream format / availability drift on
``query.wikidata.org`` and ``en.wikipedia.org``. They are skipped by default
so the regular ``pytest -m "not live"`` run stays offline and fast.

Performance budgets:

- WDQS round-trip for the current year: < 15 seconds
- Wikipedia round-trip for the current year: < 10 seconds

The previous per-country pagination strategy timed out / hung at any budget.
"""

from __future__ import annotations

import socket
import time
import urllib.error
from datetime import date

import httpx
import pytest

from app.ingest.wikidata import (
    USER_AGENT,
    fetch_elections_sparql,
    sparql_client,
)
from app.ingest.wikipedia_calendar import fetch_elections_wikipedia

pytestmark = pytest.mark.live


def _current_year() -> int:
    return date.today().year


def _next_year() -> int:
    return _current_year() + 1


def _skip_if_wdqs_degraded(exc: BaseException) -> None:
    """Skip (don't fail) when WDQS itself is rate-limiting or in an outage.

    The point of the live budget test is to detect *our* regressions; an
    upstream outage at query.wikidata.org is not actionable from this repo.
    The fallback path is exercised by the offline ``test_run_year_falls_back_*``
    tests and the live ``test_wikipedia_round_trip_under_10s`` below.
    """
    if isinstance(exc, urllib.error.HTTPError) and exc.code in (429, 500, 502, 503, 504):
        pytest.skip(f"WDQS upstream degraded (HTTP {exc.code}): {exc.reason}")
    if isinstance(exc, (TimeoutError, socket.timeout)):
        pytest.skip(f"WDQS upstream timed out: {exc!r}")
    if isinstance(exc, urllib.error.URLError):
        pytest.skip(f"WDQS unreachable: {exc.reason!r}")


def test_wdqs_round_trip_under_15s():
    year = _current_year()
    sw = sparql_client()
    t0 = time.perf_counter()
    try:
        rows = fetch_elections_sparql(
            sw,
            date_from=date(year, 1, 1),
            date_to=date(year + 1, 1, 1),
        )
    except BaseException as exc:
        _skip_if_wdqs_degraded(exc)
        raise
    elapsed = time.perf_counter() - t0

    assert elapsed < 15.0, (
        f"WDQS round-trip took {elapsed:.2f}s, exceeds 15s budget. "
        "Likely the query no longer optimizes well; inspect the SPARQL or "
        "try off-peak."
    )
    assert len(rows) >= 1, "Wikidata returned 0 European elections; suspicious."

    for r in rows:
        assert len(r.country_iso2) == 2, f"bad ISO2 {r.country_iso2!r} for {r.qid}"
        assert r.country_iso2.isalpha()
        assert r.country_iso2 == r.country_iso2.upper()
        assert isinstance(r.election_date, date)
        assert r.election_date.year == year
        assert r.qid.startswith("Q")


def test_wdqs_handles_two_year_window():
    """Sanity: a 24-month window still completes inside the budget."""
    sw = sparql_client()
    t0 = time.perf_counter()
    try:
        rows = fetch_elections_sparql(
            sw,
            date_from=date(_current_year(), 1, 1),
            date_to=date(_next_year() + 1, 1, 1),
        )
    except BaseException as exc:
        _skip_if_wdqs_degraded(exc)
        raise
    elapsed = time.perf_counter() - t0
    assert elapsed < 20.0, f"WDQS 2-year window took {elapsed:.2f}s"
    assert rows  # some European country has at least one election in 24 months


def test_wikipedia_round_trip_under_10s():
    year = _current_year()
    t0 = time.perf_counter()
    with httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=10.0,
        follow_redirects=True,
    ) as client:
        rows = fetch_elections_wikipedia(client, year=year)
    elapsed = time.perf_counter() - t0

    assert elapsed < 10.0, (
        f"Wikipedia round-trip took {elapsed:.2f}s, exceeds 10s budget."
    )
    assert len(rows) >= 1, (
        f"Wikipedia 'Elections_in_{year}' returned 0 European rows; "
        "page may have changed format."
    )

    for r in rows:
        assert len(r.country_iso2) == 2
        assert r.election_date.year == year
        assert r.qid.startswith("wp-")
