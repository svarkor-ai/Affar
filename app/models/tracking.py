"""DeliveryTrack + TrackingEvent aggregates (contract C20, rev-3).

rev-3: `carrier` is a closed enum (or NULL) — no free text on the wire. The public
lookup is keyed ONLY by the generated, non-sequential `tracking_id` (NOT the orders.id
PK), so orders are not enumerable (refutation 3 fix, I5).
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

TRACK_EVENT: tuple[str, ...] = (
    "placed",
    "in-warehouse",
    "in-transit",
    "out-for-delivery",
    "delivered",
)

# CLOSED set — no free text (rev-3). NULL (no carrier yet) is allowed.
CARRIER: tuple[str, ...] = ("postnord", "bring", "schenker", "dhl", "own-fleet")


class DeliveryTrack(Base):
    __tablename__ = "delivery_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"), nullable=False, unique=True
    )
    carrier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # THE one public identifier — generated, non-sequential, high-entropy
    # (secrets.token_hex(16)). Created with the track on first event (C20).
    tracking_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    order: Mapped["Order"] = relationship("Order")
    events: Mapped[list["TrackingEvent"]] = relationship(
        "TrackingEvent",
        back_populates="delivery_track",
        cascade="all, delete-orphan",
        order_by="TrackingEvent.at",
    )

    def __repr__(self) -> str:
        return f"<DeliveryTrack(id={self.id}, tracking_id={self.tracking_id!r})>"


class TrackingEvent(Base):
    __tablename__ = "tracking_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    delivery_track_id: Mapped[int] = mapped_column(
        ForeignKey("delivery_tracks.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Staff internal free text (C20); never emitted on the public surface (C21 rev-2).
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )

    delivery_track: Mapped["DeliveryTrack"] = relationship(
        "DeliveryTrack", back_populates="events"
    )

    def __repr__(self) -> str:
        return f"<TrackingEvent(id={self.id}, status={self.status!r})>"
