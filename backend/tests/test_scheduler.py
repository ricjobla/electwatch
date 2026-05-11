"""Scheduler wiring for Phase 3 live scrape cycles."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from app.models.country import Country
from app.models.election import Election


def _poll_with_fixture_db(db_session):
    """``run_live_poll_cycle`` uses ``SessionLocal()`` — patch it to the test SQLite pool."""
    from app.scheduler import run_live_poll_cycle

    with patch("app.scheduler.SessionLocal", return_value=db_session):
        with patch.object(db_session, "close", lambda: None):
            run_live_poll_cycle()


@patch("app.scheduler.date")
def test_run_live_poll_cycle_calls_scraper_for_qualifying_election(
    mock_date,
    db_session,
):
    """Elections for scraped countries, on or before ``today``, upcoming/live → scraper.run."""
    mock_date.today.return_value = date(2026, 5, 30)

    db_session.add(
        Country(id="MT", name="Malta", region="Europe / Southern Europe"),
    )
    db_session.add(
        Election(
            id="MT-2026-parliament",
            country_id="MT",
            type="parliamentary",
            election_date=date(2026, 5, 30),
            status="upcoming",
            title="Malta general election (fixture)",
        ),
    )
    db_session.commit()

    mock_run = MagicMock()
    with patch(
        "app.ingest.scrapers.malta.MaltaScraper.run",
        mock_run,
    ):
        _poll_with_fixture_db(db_session)

    mock_run.assert_called_once()


@patch("app.scheduler.date")
def test_run_live_poll_cycle_skips_future_election(mock_date, db_session):
    mock_date.today.return_value = date(2026, 5, 29)

    db_session.add(
        Country(id="MT", name="Malta", region="Europe / Southern Europe"),
    )
    db_session.add(
        Election(
            id="MT-future",
            country_id="MT",
            type="parliamentary",
            election_date=date(2026, 5, 30),
            status="upcoming",
            title="Tomorrow",
        ),
    )
    db_session.commit()

    mock_run = MagicMock()
    with patch(
        "app.ingest.scrapers.malta.MaltaScraper.run",
        mock_run,
    ):
        _poll_with_fixture_db(db_session)

    mock_run.assert_not_called()
