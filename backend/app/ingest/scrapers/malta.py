from app.ingest.scrapers.base import BaseScraper, ScrapeOutcome, parse_generic_results_table


class MaltaScraper(BaseScraper):
    """Official Maltese electoral commission pages (HTML tables)."""

    country_id = "MT"

    @property
    def default_results_url(self) -> str:
        return "https://electoral.gov.mt/en/election-results/"

    def parse_page(self, html: str) -> ScrapeOutcome:
        return parse_generic_results_table(html)
