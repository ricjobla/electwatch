from app.ingest.scrapers.base import BaseScraper, ScrapeOutcome, parse_generic_results_table


class CyprusScraper(BaseScraper):
    """Cyprus Chief Returning Officer publications (HTML tables)."""

    country_id = "CY"

    @property
    def default_results_url(self) -> str:
        return "https://www.elections.gov.cy/"

    def parse_page(self, html: str) -> ScrapeOutcome:
        return parse_generic_results_table(html)
