from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.country import Country
    from app.models.result import Result


class Party(Base):
    __tablename__ = "parties"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    country_id: Mapped[str | None] = mapped_column(
        String(2), ForeignKey("countries.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    short_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    color_hex: Mapped[str | None] = mapped_column(Text, nullable=True)
    wikidata_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    ideology: Mapped[str | None] = mapped_column(Text, nullable=True)

    country: Mapped["Country | None"] = relationship(
        "Country", back_populates="parties"
    )
    results: Mapped[list["Result"]] = relationship("Result", back_populates="party")
