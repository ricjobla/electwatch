from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.election import Election
from app.models.ingest_log import IngestLog
from app.models.party import Party
from app.models.result import Result

log = logging.getLogger(__name__)

USER_AGENT = (
    "ElectWatch/0.1 (+https://github.com/electwatch; election-results aggregator)"
)


@dataclass
class PartyRow:
    party_name: str
    vote_share: float | None = None
    seats_won: int | None = None
    votes_raw: int | None = None


@dataclass
class ScrapeOutcome:
    rows: list[PartyRow] = field(default_factory=list)
    is_final: bool = False
    reporting_pct: float | None = None
    turnout_pct: float | None = None


def _slug_party_id(country_id: str, party_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", party_name.lower()).strip("-")[:96]
    if not slug:
        slug = "unknown"
    return f"{country_id.upper()}-{slug}"


def normalize_pct_cell(text: str) -> float | None:
    t = text.strip().replace("\xa0", " ")
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%?", t.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def normalize_int_cell(text: str) -> int | None:
    t = re.sub(r"[^\d]", "", text.strip())
    if not t:
        return None
    try:
        return int(t)
    except ValueError:
        return None


class BaseScraper(ABC):
    """Fetch official HTML results, parse rows, upsert parties/results, update election status."""

    country_id: str

    def __init__(self, election_id: str, db: Session) -> None:
        self.election_id = election_id
        self.db = db

    @property
    @abstractmethod
    def default_results_url(self) -> str: ...

    def _log(self, status: str, message: str) -> None:
        self.db.add(
            IngestLog(
                source=f"scraper.{self.country_id}",
                election_id=self.election_id,
                status=status,
                message=message[:4000],
            )
        )
        self.db.commit()

    def fetch_html(self, url: str, retries: int = 3) -> str:
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                with httpx.Client(
                    timeout=40.0,
                    headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
                    follow_redirects=True,
                ) as client:
                    r = client.get(url)
                    r.raise_for_status()
                    return r.text
            except Exception as exc:
                last_err = exc
                wait = 1.5 * (attempt + 1)
                log.warning("fetch %s attempt %s failed: %s", url, attempt + 1, exc)
                time.sleep(wait)
        assert last_err is not None
        raise last_err

    @abstractmethod
    def parse_page(self, html: str) -> ScrapeOutcome:
        """Parse downloaded HTML into structured rows."""

    def scrape(self, election: Election) -> ScrapeOutcome:
        url = (election.source_url or "").strip() or self.default_results_url
        html = self.fetch_html(url)
        return self.parse_page(html)

    def _ensure_parties_and_results(self, election: Election, outcome: ScrapeOutcome) -> None:
        cid = election.country_id or self.country_id
        now = datetime.now(timezone.utc)
        res_type = "final" if outcome.is_final else "partial"

        self.db.execute(delete(Result).where(Result.election_id == election.id))

        for row in outcome.rows:
            name = row.party_name.strip()
            if not name:
                continue
            pid = _slug_party_id(cid, name)
            party = self.db.get(Party, pid)
            if party is None:
                party = Party(id=pid, country_id=cid, name=name)
                self.db.add(party)
            elif party.name != name:
                party.name = name
            self.db.flush()

            self.db.add(
                Result(
                    election_id=election.id,
                    party_id=pid,
                    vote_share=row.vote_share,
                    seats_won=row.seats_won,
                    votes_raw=row.votes_raw,
                    result_type=res_type,
                )
            )

        election.reporting_pct = outcome.reporting_pct
        if outcome.turnout_pct is not None:
            election.turnout_pct = outcome.turnout_pct
        election.last_updated = now

        if outcome.rows:
            if election.status == "upcoming":
                election.status = "live"
            if outcome.is_final:
                election.status = "complete"

        self.db.commit()

    def run(self) -> None:
        election = self.db.get(Election, self.election_id)
        if election is None:
            self._log("error", "Election not found")
            return
        if election.status == "complete":
            return
        if election.country_id and election.country_id.upper() != self.country_id:
            self._log("skipped", "Country mismatch for scraper")
            return

        try:
            outcome = self.scrape(election)
        except Exception as exc:
            log.exception("scrape failed for %s", self.election_id)
            self._log("error", str(exc))
            return

        if not outcome.rows:
            self._log("skipped", "No result rows parsed (page layout or not yet posted)")
            return

        try:
            self._ensure_parties_and_results(election, outcome)
        except Exception as exc:
            log.exception("persist failed for %s", self.election_id)
            self._log("error", f"persist: {exc}")
            return

        self._log(
            "success",
            f"rows={len(outcome.rows)} final={outcome.is_final} reporting={outcome.reporting_pct}",
        )


def parse_generic_results_table(html: str) -> ScrapeOutcome:
    """Best-effort extraction from the largest HTML table with party-like rows."""
    soup = BeautifulSoup(html, "html.parser")
    best_rows: list[list[str]] = []
    best_table_score = 0

    for table in soup.find_all("table"):
        raw_rows: list[list[str]] = []
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            texts = [c.get_text(" ", strip=True) for c in cells]
            if len(texts) >= 2:
                raw_rows.append(texts)
        if len(raw_rows) < 2:
            continue
        header = [c.lower() for c in raw_rows[0]]
        has_party = any(
            any(k in h for k in ("party", "candidate", "coalition", "movement"))
            for h in header
        )
        score = len(raw_rows) + (3 if has_party else 0)
        if score > best_table_score:
            best_table_score = score
            best_rows = raw_rows

    if len(best_rows) < 2:
        return ScrapeOutcome()

    header = [c.lower() for c in best_rows[0]]
    col_party = next(
        (
            i
            for i, h in enumerate(header)
            if any(k in h for k in ("party", "candidate", "coalition", "movement", "name"))
        ),
        0,
    )
    col_pct = next(
        (i for i, h in enumerate(header) if "%" in h or "percent" in h or h.strip() == "%"),
        None,
    )
    col_seats = next(
        (i for i, h in enumerate(header) if "seat" in h or "mandat" in h),
        None,
    )
    col_votes = next(
        (i for i, h in enumerate(header) if "vote" in h and "turnout" not in h),
        None,
    )

    rows_out: list[PartyRow] = []
    data_rows = best_rows[1:]
    for cells in data_rows:
        if col_party >= len(cells):
            continue
        name = cells[col_party].strip()
        if not name or len(name) > 200:
            continue
        lower = name.lower()
        if lower in ("total", "valid votes", "registered voters", "turnout"):
            continue

        pct = None
        if col_pct is not None and col_pct < len(cells):
            pct = normalize_pct_cell(cells[col_pct])
        if pct is None:
            for j, c in enumerate(cells):
                if j != col_party and normalize_pct_cell(c) is not None:
                    pct = normalize_pct_cell(c)
                    break

        seats = None
        if col_seats is not None and col_seats < len(cells):
            seats = normalize_int_cell(cells[col_seats])

        votes = None
        if col_votes is not None and col_votes < len(cells):
            votes = normalize_int_cell(cells[col_votes])

        rows_out.append(
            PartyRow(
                party_name=name,
                vote_share=pct,
                seats_won=seats,
                votes_raw=votes,
            )
        )

    reporting_pct: float | None = None
    text_lower = soup.get_text("\n", strip=True).lower()
    for pat in (
        r"(\d+(?:\.\d+)?)\s*%\s*(?:of\s*)?(?:polling\s*)?(?:stations?\s*)?(?:reporting|counted)",
        r"(?:reporting|counted)\s*:?\s*(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s*processed",
    ):
        m = re.search(pat, text_lower)
        if m:
            try:
                reporting_pct = float(m.group(1))
                break
            except ValueError:
                pass

    turnout_pct: float | None = None
    tm = re.search(
        r"turnout\s*:?\s*(\d+(?:\.\d+)?)\s*%",
        text_lower,
    )
    if tm:
        try:
            turnout_pct = float(tm.group(1))
        except ValueError:
            pass

    is_final = bool(
        re.search(
            r"(final\s+(results|result)|official\s+(results|result)|scrutiny\s+completed)",
            text_lower,
        )
    )

    return ScrapeOutcome(
        rows=rows_out,
        is_final=is_final,
        reporting_pct=reporting_pct,
        turnout_pct=turnout_pct,
    )
