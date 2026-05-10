"""Offline tests for the Wikipedia 'Elections in YYYY' fallback parser."""

from __future__ import annotations

from datetime import date

import httpx

from app.ingest.wikipedia_calendar import (
    fetch_elections_wikipedia,
    parse_elections_html,
)


def test_parse_elections_in_2026(wikipedia_2026_html):
    rows = parse_elections_html(wikipedia_2026_html, year=2026)

    iso_codes = [r.country_iso2 for r in rows]
    iso_set = set(iso_codes)

    # Each European demonym should be inferred at least once.
    assert {"BG", "CY", "CZ", "HU", "MT", "ME", "SE", "GB"} <= iso_set

    # Non-European countries (United States, Morocco) must be filtered.
    assert "US" not in iso_set
    assert "MA" not in iso_set

    # Wrong-year reference ("2025 Icelandic municipal elections") must be filtered.
    assert "IS" not in iso_set

    # Two UK rows in the fixture must both survive (distinct slug qids).
    assert iso_codes.count("GB") == 2

    cy_rows = [r for r in rows if r.country_iso2 == "CY"]
    assert len(cy_rows) == 1
    cy = cy_rows[0]
    assert cy.election_date == date(2026, 5, 24)
    assert cy.country_iso2 == "CY"
    assert cy.qid.startswith("wp-CY-2026-05-24-")
    assert cy.election_uri is None
    assert cy.country_qid is None
    assert cy.wikipedia_url and cy.wikipedia_url.startswith("https://en.wikipedia.org/wiki/")
    assert "Cypriot" in cy.title

    # Czech Senate election uses an en-dash range "9–10 October"; the parser
    # should pick the first usable date.
    cz_rows = [r for r in rows if r.country_iso2 == "CZ"]
    assert cz_rows
    assert cz_rows[0].election_date.month == 10


def test_unknown_country_is_skipped_not_raised():
    """A bullet whose title has no European demonym is dropped silently."""
    html = """
    <ul>
      <li><a href="/wiki/2026_Atlantian_general_election">2026 Atlantian general election</a>, 1 May</li>
      <li><a href="/wiki/2026_Cypriot_legislative_election">2026 Cypriot legislative election</a>, 2 May</li>
    </ul>
    """
    rows = parse_elections_html(html, year=2026)
    assert len(rows) == 1
    assert rows[0].country_iso2 == "CY"


def test_non_european_demonym_collisions_are_skipped():
    """'British Columbia' is in Canada; the trailing 'British' must not tag it GB."""
    html = """
    <ul>
      <li><a href="/wiki/2026_British_Columbia_municipal_elections">2026 British Columbia municipal elections</a>, 17 October</li>
      <li><a href="/wiki/2026_French_Polynesian_election">2026 French Polynesian election</a>, 1 May</li>
      <li><a href="/wiki/2026_British_general_election">2026 British general election</a>, 4 June</li>
    </ul>
    """
    rows = parse_elections_html(html, year=2026)
    isos = [r.country_iso2 for r in rows]
    # The genuine UK row stays; the BC and Polynesia rows are dropped.
    assert isos == ["GB"]
    assert "British general election" in rows[0].title


def test_pseudo_qids_are_unique_and_deterministic(wikipedia_2026_html):
    rows1 = parse_elections_html(wikipedia_2026_html, year=2026)
    rows2 = parse_elections_html(wikipedia_2026_html, year=2026)
    assert [r.qid for r in rows1] == [r.qid for r in rows2]
    assert len({r.qid for r in rows1}) == len(rows1)


def test_fetch_uses_parsoid_first_then_falls_back_to_raw():
    """If Parsoid returns 404, the raw page render is tried."""
    raw_html = """
    <ul>
      <li><a href="/wiki/2026_Spanish_general_election">2026 Spanish general election</a>, 3 May</li>
    </ul>
    """
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if "/api/rest_v1/" in str(request.url):
            return httpx.Response(404, text="not found")
        return httpx.Response(200, text=raw_html)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        rows = fetch_elections_wikipedia(client, year=2026)

    assert len(seen_urls) == 2
    assert "rest_v1" in seen_urls[0]
    assert "action=raw" in seen_urls[1]
    assert len(rows) == 1
    assert rows[0].country_iso2 == "ES"
    assert rows[0].election_date == date(2026, 5, 3)


def test_fetch_uses_parsoid_when_available(wikipedia_2026_html):
    seen_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, text=wikipedia_2026_html)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        rows = fetch_elections_wikipedia(client, year=2026)

    assert len(seen_urls) == 1
    assert "rest_v1" in seen_urls[0]
    assert any(r.country_iso2 == "MT" for r in rows)
