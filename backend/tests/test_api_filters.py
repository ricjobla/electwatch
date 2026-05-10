"""End-to-end tests for the API filters introduced in Phase 2.

These run against a fresh in-memory SQLite database that we seed directly via
the SQLAlchemy models — no network and no ParlGov fixtures required.
"""

from __future__ import annotations

from datetime import date

import pytest


def _seed(db_session) -> None:
    from app.models.country import Country
    from app.models.election import Election

    db_session.add_all([
        Country(id="SE", name="Sweden", region="Europe / Northern Europe"),
        Country(id="CY", name="Cyprus", region="Europe / Southern Europe"),
        Country(id="DE", name="Germany", region="Europe / Western Europe"),
    ])
    db_session.flush()

    db_session.add_all([
        Election(
            id="se-2022-09-11",
            country_id="SE",
            type="parliamentary",
            election_date=date(2022, 9, 11),
            status="complete",
            title="Sweden — parliamentary — 2022-09-11",
        ),
        Election(
            id="cy-2026-05-24",
            country_id="CY",
            type=None,  # Wikidata rows arrive without a type
            election_date=date(2026, 5, 24),
            status="upcoming",
            title="2026 Cypriot parliamentary election",
        ),
        Election(
            id="de-2025-09-21",
            country_id="DE",
            type="european_parliament",
            election_date=date(2025, 9, 21),
            status="complete",
            title="Germany — European Parliament — 2025-09-21",
        ),
    ])
    db_session.commit()


@pytest.fixture()
def client(db_session):
    """FastAPI client with the in-memory DB injected via dependency override."""
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    _seed(db_session)

    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_calendar_no_filter_returns_all(client):
    r = client.get("/api/calendar", params={"limit": 50})
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()["elections"]}
    assert ids == {"se-2022-09-11", "cy-2026-05-24", "de-2025-09-21"}


def test_calendar_type_filter_parliamentary(client):
    r = client.get("/api/calendar", params={"type": "parliamentary"})
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()["elections"]}
    # Substring match: 'parliamentary' must hit Sweden, but NOT the German EU
    # row whose type is 'european_parliament' (no 'parliamentary' substring).
    assert ids == {"se-2022-09-11"}


def test_calendar_type_filter_is_case_insensitive(client):
    r = client.get("/api/calendar", params={"type": "PARLIAMENTARY"})
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()["elections"]}
    assert ids == {"se-2022-09-11"}


def test_calendar_type_filter_european_parliament(client):
    r = client.get("/api/calendar", params={"type": "european_parliament"})
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()["elections"]}
    assert ids == {"de-2025-09-21"}


def test_calendar_country_filter(client):
    r = client.get("/api/calendar", params={"country": "CY"})
    assert r.status_code == 200
    ids = [e["id"] for e in r.json()["elections"]]
    assert ids == ["cy-2026-05-24"]


def test_calendar_combined_status_and_region(client):
    r = client.get(
        "/api/calendar",
        params={
            "from": "2026-01-01",
            "to": "2026-12-31",
            "region": "europe",
            "status": "upcoming",
        },
    )
    assert r.status_code == 200
    rows = r.json()["elections"]
    assert len(rows) == 1
    assert rows[0]["country_id"] == "CY"
    assert rows[0]["election_date"] == "2026-05-24"


def test_elections_types_endpoint(client):
    r = client.get("/api/elections/types")
    assert r.status_code == 200
    body = r.json()
    assert body == ["european_parliament", "parliamentary"]


def test_elections_list_type_filter(client):
    r = client.get("/api/elections", params={"type": "european"})
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()["elections"]}
    assert ids == {"de-2025-09-21"}


def test_country_elections_endpoint(client):
    r = client.get("/api/countries/SE/elections")
    assert r.status_code == 200
    rows = r.json()["elections"]
    assert [e["id"] for e in rows] == ["se-2022-09-11"]


def test_election_detail_endpoint(client):
    r = client.get("/api/elections/se-2022-09-11")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "se-2022-09-11"
    assert body["country_id"] == "SE"
    assert body["country"]["name"] == "Sweden"
    assert body["results"] == []
