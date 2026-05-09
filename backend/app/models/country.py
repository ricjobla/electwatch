from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.election import Election
    from app.models.party import Party


class Country(Base):
    __tablename__ = "countries"

    id: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str] = mapped_column(Text, nullable=False)
    flag_emoji: Mapped[str | None] = mapped_column(Text, nullable=True)
    wikidata_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    elections: Mapped[list["Election"]] = relationship(
        "Election", back_populates="country"
    )
    parties: Mapped[list["Party"]] = relationship("Party", back_populates="country")
