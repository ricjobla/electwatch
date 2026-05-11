"""Shared pytest fixtures.

The DB fixture wires SQLAlchemy to an in-memory SQLite engine *before* any of
``app.database`` is imported elsewhere, so application code that calls
``SessionLocal()`` / ``get_db()`` automatically uses the test DB.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_BACKEND = Path(__file__).resolve().parent.parent

# Force the in-memory SQLite engine before app.database is imported anywhere.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SCRAPER_SCHEDULER_ENABLED", "false")

# Allow `import app...` from the backend package without a pip install.
if str(REPO_BACKEND) not in sys.path:
    sys.path.insert(0, str(REPO_BACKEND))


FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fixture_dir() -> Path:
    return FIXTURE_DIR


@pytest.fixture(scope="session")
def wdqs_2026_sample(fixture_dir: Path) -> dict:
    return json.loads((fixture_dir / "wdqs_2026_sample.json").read_text())


@pytest.fixture(scope="session")
def wikipedia_2026_html(fixture_dir: Path) -> str:
    return (fixture_dir / "wikipedia_elections_2026.html").read_text()


@pytest.fixture()
def db_session():
    """Fresh in-memory SQLite session per test, with all tables created.

    ``StaticPool`` is required so the entire test (including any extra
    connections checked out by FastAPI dependency overrides) sees the same
    in-memory database — without it each ``:memory:`` connection has its own
    private DB.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    # Ensure all model classes are registered on Base.metadata.
    import app.models  # noqa: F401

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
