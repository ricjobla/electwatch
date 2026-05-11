"""Tests for Phase 3 live listing endpoint."""

from __future__ import annotations

from datetime import date

import pytest


@pytest.fixture()
def client_live(db_session):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app
    from app.models.country import Country
    from app.models.election import Election

    db_session.add(
        Country(id="MT", name="Malta", region="Europe / Southern Europe"),
    )
    db_session.add_all(
        [
            Election(
                id="mt-2026-live",
                country_id="MT",
                type="parliamentary",
                election_date=date(2026, 5, 30),
                status="live",
                title="Malta — general election — 2026 (live fixture)",
                reporting_pct=48.2,
            ),
            Election(
                id="mt-2026-upcoming",
                country_id="MT",
                type="parliamentary",
                election_date=date(2027, 1, 1),
                status="upcoming",
                title="Future placeholder",
            ),
        ]
    )
    db_session.commit()

    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_live_endpoint_returns_only_live_rows(client_live):
    r = client_live.get("/api/live")
    assert r.status_code == 200
    body = r.json()
    assert len(body["elections"]) == 1
    row = body["elections"][0]
    assert row["id"] == "mt-2026-live"
    assert row["status"] == "live"
    assert row["reporting_pct"] == pytest.approx(48.2)
