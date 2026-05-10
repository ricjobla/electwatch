"""Offline tests for the SPARQL ingest path."""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import pytest
from SPARQLWrapper.SPARQLExceptions import EndPointInternalError

from app.ingest import wikidata
from app.ingest.wikidata import (
    ElectionRow,
    _rows_from_bindings,
    build_sparql_query,
    run_year,
)
from app.models.election import Election
from app.models.ingest_log import IngestLog


class _FakeSPARQLResult:
    def __init__(self, payload: dict):
        self._payload = payload

    def convert(self) -> dict:
        return self._payload


class _FakeSPARQL:
    """Minimal SPARQLWrapper stand-in: capture query, return canned payload."""

    def __init__(self, payload: dict | None = None, raise_exc: BaseException | None = None):
        self._payload = payload or {"results": {"bindings": []}}
        self._raise_exc = raise_exc
        self.last_query: str | None = None

    def setQuery(self, q: str) -> None:
        self.last_query = q

    def query(self) -> _FakeSPARQLResult:
        if self._raise_exc is not None:
            raise self._raise_exc
        return _FakeSPARQLResult(self._payload)


def test_sparql_query_text_is_range_safe():
    q = build_sparql_query(date_from=date(2026, 1, 1), date_to=date(2027, 1, 1))
    assert "hint:rangeSafe" in q
    assert "xsd:dateTime" in q
    assert "wdt:P30  wd:Q46" in q or "wdt:P30 wd:Q46" in q
    assert "wdt:P297" in q
    assert "P279*" in q
    assert "YEAR(" not in q
    assert "MONTH(" not in q
    assert "2026-01-01" in q
    assert "2027-01-01" in q


def test_sparql_parses_rows(wdqs_2026_sample):
    """Same Q-id rows collapse; distinct Q-ids on the same date do not."""
    bindings = wdqs_2026_sample["results"]["bindings"]
    rows = _rows_from_bindings(bindings)

    # 5 unique elections + 1 distinct Cypriot row at same date = 6.
    # The two `Q108696420` bindings collapse to one.
    assert len(rows) == 6
    qids = [r.qid for r in rows]
    assert qids.count("Q108696420") == 1

    by_qid = {r.qid: r for r in rows}
    cy = by_qid["Q108696420"]
    assert cy.country_iso2 == "CY"
    assert cy.country_name == "Cyprus"
    assert cy.election_date == date(2026, 5, 24)
    assert cy.country_qid == "Q229"
    assert cy.title == "2026 Cypriot parliamentary election"
    assert cy.election_uri == "http://www.wikidata.org/entity/Q108696420"

    mt = by_qid["Q113054321"]
    assert mt.country_iso2 == "MT"
    assert mt.election_date == date(2026, 5, 30)


def test_run_year_upserts_and_logs(db_session, wdqs_2026_sample):
    sw = _FakeSPARQL(payload=wdqs_2026_sample)
    stats = run_year(
        db_session,
        year=2026,
        source="sparql",
        sparql=sw,
    )

    assert stats["source"] == "sparql"
    assert stats["rows_fetched"] == 6
    assert stats["upserted"] == 6
    assert stats["skipped"] == 0
    assert stats["sparql_error"] is None

    elections = db_session.query(Election).order_by(
        Election.election_date, Election.id
    ).all()
    assert [e.election_date for e in elections] == [
        date(2026, 4, 12),
        date(2026, 5, 24),
        date(2026, 5, 24),
        date(2026, 5, 30),
        date(2026, 6, 7),
        date(2026, 9, 13),
    ]
    cy_election = db_session.get(Election, "wikidata-Q108696420")
    assert cy_election is not None
    assert cy_election.country_id == "CY"
    assert cy_election.wikidata_id == "Q108696420"
    assert cy_election.source_url == "https://www.wikidata.org/wiki/Q108696420"

    logs = db_session.query(IngestLog).filter(IngestLog.source == "wikidata").all()
    assert len(logs) == 6
    assert all(log.status == "success" for log in logs)


def test_run_year_dry_run_does_not_write(db_session, wdqs_2026_sample, capsys):
    sw = _FakeSPARQL(payload=wdqs_2026_sample)
    stats = run_year(
        db_session,
        year=2026,
        source="sparql",
        sparql=sw,
        dry_run=True,
    )

    assert stats["dry_run"] is True
    assert stats["rows_fetched"] == 6
    assert stats["upserted"] == 0
    assert db_session.query(Election).count() == 0

    out = capsys.readouterr().out
    assert "2026-05-24" in out
    assert "Cyprus" in out or "CY" in out


def test_run_year_months_filter(db_session, wdqs_2026_sample):
    sw = _FakeSPARQL(payload=wdqs_2026_sample)
    stats = run_year(
        db_session,
        year=2026,
        source="sparql",
        sparql=sw,
        months=[5],
    )
    assert stats["months_filter"] == [5]
    # May = both Cypriot rows (parliamentary + presidential) + Maltese = 3
    assert stats["rows_fetched"] == 3
    assert stats["upserted"] == 3
    qids = {e.wikidata_id for e in db_session.query(Election).all()}
    assert qids == {"Q108696420", "Q120000004", "Q113054321"}


def _wikipedia_mock_transport(html: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html)

    return httpx.MockTransport(handler)


def test_run_year_falls_back_to_wikipedia(db_session, wikipedia_2026_html):
    sw = _FakeSPARQL(raise_exc=EndPointInternalError("simulated WDQS 500"))
    transport = _wikipedia_mock_transport(wikipedia_2026_html)
    with httpx.Client(transport=transport) as client:
        stats = run_year(
            db_session,
            year=2026,
            source="auto",
            sparql=sw,
            http=client,
        )

    assert stats["source"] == "wikipedia"
    assert stats["sparql_error"] and "EndPointInternalError" in stats["sparql_error"]
    assert stats["upserted"] >= 4  # CY, MT, CZ, ME, SE — non-European rows filtered

    isos = {e.country_id for e in db_session.query(Election).all()}
    assert {"CY", "MT", "CZ", "ME", "SE"} <= isos
    assert "US" not in isos  # not European, must be filtered


def test_run_year_source_sparql_does_not_fall_back(db_session):
    sw = _FakeSPARQL(raise_exc=EndPointInternalError("simulated WDQS 500"))
    with pytest.raises(EndPointInternalError):
        run_year(db_session, year=2026, source="sparql", sparql=sw)
    assert db_session.query(Election).count() == 0


def test_election_row_shape_is_consistent_for_both_paths(wdqs_2026_sample, wikipedia_2026_html):
    """Both paths must produce ElectionRow values that can feed upsert_election_row."""
    from app.ingest.wikipedia_calendar import parse_elections_html

    sparql_rows = _rows_from_bindings(wdqs_2026_sample["results"]["bindings"])
    wiki_rows = parse_elections_html(wikipedia_2026_html, year=2026)

    assert sparql_rows and wiki_rows
    assert all(isinstance(r, ElectionRow) for r in sparql_rows)
    assert all(isinstance(r, ElectionRow) for r in wiki_rows)
    for r in sparql_rows + wiki_rows:
        assert len(r.country_iso2) == 2
        assert isinstance(r.election_date, date)
        assert r.qid
        assert r.title
