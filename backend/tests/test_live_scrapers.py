from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def malta_html() -> str:
    return (FIXTURE_DIR / "malta_results_sample.html").read_text()


def test_parse_generic_results_table_extracts_rows(malta_html: str):
    from app.ingest.scrapers.base import parse_generic_results_table

    out = parse_generic_results_table(malta_html)
    assert len(out.rows) >= 2
    names = {r.party_name for r in out.rows}
    assert "Labour Party" in names
    assert out.reporting_pct is not None and out.reporting_pct > 40


def test_malta_scraper_run_persists_results(db_session, malta_html: str):
    from app.ingest.scrapers.malta import MaltaScraper
    from app.models.country import Country
    from app.models.election import Election

    db_session.add(
        Country(id="MT", name="Malta", region="Europe / Southern Europe"),
    )
    db_session.add(
        Election(
            id="MT-test-parliament",
            country_id="MT",
            type="parliamentary",
            election_date=date(2026, 5, 30),
            status="upcoming",
            title="Malta general election (test)",
            source_url="https://electoral.gov.mt/example",
        ),
    )
    db_session.commit()

    scraper = MaltaScraper("MT-test-parliament", db_session)
    with patch.object(MaltaScraper, "fetch_html", return_value=malta_html):
        scraper.run()

    db_session.expire_all()
    election = db_session.get(Election, "MT-test-parliament")
    assert election is not None
    assert election.status == "live"
    assert len(election.results) >= 2
    assert all((r.result_type == "partial") for r in election.results)
