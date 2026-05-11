"""Country-specific live result scrapers (Phase 3)."""

from app.ingest.scrapers.cyprus import CyprusScraper
from app.ingest.scrapers.malta import MaltaScraper

SCRAPER_CLASSES = {
    "CY": CyprusScraper,
    "MT": MaltaScraper,
}


def scraper_for_country(country_id: str | None):
    if not country_id:
        return None
    return SCRAPER_CLASSES.get(country_id.upper())
