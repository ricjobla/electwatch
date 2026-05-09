from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Integer, Text, false, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.election import Election
    from app.models.party import Party


class Result(Base):
    __tablename__ = "results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    election_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("elections.id"), nullable=True
    )
    party_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("parties.id"), nullable=True
    )
    vote_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    seats_won: Mapped[int | None] = mapped_column(Integer, nullable=True)
    votes_raw: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_governing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    result_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'final'"),
    )

    election: Mapped["Election | None"] = relationship(
        "Election", back_populates="results"
    )
    party: Mapped["Party | None"] = relationship("Party", back_populates="results")
