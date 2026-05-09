from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Float, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.country import Country
    from app.models.result import Result


class Election(Base):
    __tablename__ = "elections"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    country_id: Mapped[str | None] = mapped_column(
        String(2), ForeignKey("countries.id"), nullable=True
    )
    type: Mapped[str | None] = mapped_column(Text, nullable=True)
    election_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'upcoming'"),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    wikipedia_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    wikidata_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    turnout_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_updated: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    country: Mapped["Country | None"] = relationship(
        "Country", back_populates="elections"
    )
    results: Mapped[list["Result"]] = relationship(
        "Result", back_populates="election"
    )
