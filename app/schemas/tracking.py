"""Public tracking wire schemas (contract C20 rev-3 / C21 rev-2).

These are the ONLY shapes the public ``GET /api/tracking/{tracking_id}`` route
may emit. The sanitisation rules are baked in at the schema level:

  * ``DeliveryTrackOut`` exposes the public ``tracking_id`` (the generated,
    non-sequential public key - I5), the ``carrier`` and the current ``status``.
    It NEVER carries the internal primary key / order id or ``tracking_ref``.
  * ``TrackingEventOut`` exposes ``status`` and ``at`` (the public timeline).
    The staff-only ``note`` field is deliberately ABSENT (C21 rev-2) - it is a
    property of the ORM row but not of this wire model, so it cannot leak.

No field here is derived from anything secret; nothing on this surface requires
authentication to read (the whole point of "publik spårning").
"""

from datetime import datetime

from pydantic import BaseModel, Field

# Import from the concrete tracking module (not the app.models umbrella) to keep
# the schema a leaf with no load-order coupling to the full model package.
from app.models.tracking import TRACK_EVENT


class TrackingEventOut(BaseModel):
    """One public timeline event - status + timestamp only (C21 rev-2)."""

    status: str
    at: datetime


class TrackingEventIn(BaseModel):
    """Staff write body for appending one tracking event (C21 rev-3).

    ``status`` must be a member of the closed TRACK_EVENT set; anything else is
    rejected server-side (no free-form status). ``note`` is optional staff free
    text (e.g. "plockas i lagret") that is stored on the ORM row but NEVER
    emitted on any public Out schema - it is a write-side-internal property.
    """

    status: str = Field(max_length=32)
    note: str | None = Field(default=None, max_length=500)

    def validate_status(self) -> None:
        from fastapi import HTTPException, status as http_status

        if self.status not in TRACK_EVENT:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"status must be one of {list(TRACK_EVENT)}",
            )


class DeliveryTrackOut(BaseModel):
    """Public representation of a delivery track.

    ``status`` is the latest timeline event's status (a convenience for the
    customer), while ``events`` is the full chronological timeline.
    ``tracking_id`` is echoed so the caller can confirm WHICH track they got,
    and ``carrier`` names the shipper once assigned (None until dispatch).
    Internal ids / tracking_ref are absent.
    """

    tracking_id: str
    carrier: str | None = None
    status: str
    events: list[TrackingEventOut]
