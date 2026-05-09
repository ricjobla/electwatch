from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class CountryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(max_length=2)
    name: str
    region: str
    flag_emoji: str | None = None
    wikidata_id: str | None = None


class CalendarElectionOut(BaseModel):
    """Election row for calendar / list views."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    election_date: date
    status: str
    type: str | None = None
    country_id: str | None = None
    country_name: str | None = None
    turnout_pct: float | None = None


class ElectionResultRow(BaseModel):
    vote_share: float | None = None
    seats_won: int | None = None
    votes_raw: int | None = None
    party_id: str | None = None
    party_name: str | None = None
    party_short_name: str | None = None
    party_color_hex: str | None = None


class ElectionDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    election_date: date
    status: str
    type: str | None = None
    country_id: str | None = None
    description: str | None = None
    wikipedia_url: str | None = None
    wikidata_id: str | None = None
    turnout_pct: float | None = None
    source_url: str | None = None
    last_updated: datetime | None = None
    country: CountryOut | None = None
    results: list[ElectionResultRow] = Field(default_factory=list)


class CalendarResponse(BaseModel):
    elections: list[CalendarElectionOut]


class ElectionsListResponse(BaseModel):
    elections: list[CalendarElectionOut]


class CountriesResponse(BaseModel):
    countries: list[CountryOut]
