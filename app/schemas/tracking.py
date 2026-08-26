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

from pydantic import BaseModel


class TrackingEventOut(BaseModel):
    """One public timeline event - status + timestamp only (C21 rev-2)."""

    status: str
    at: datetime


class DeliveryTrackOut(BaseModel):
    """Public representation of a delivery track.

    ``status`` is the latest timeline event's status (a convenience for the
    customer), while ``events`` is the full chronological timeline.
    ``tracking_id`` is echoed so the caller can confirm WHICH track they got,
    and ``carrier`` names the shipper. Internal ids / tracking_ref are absent.
    """

    tracking_id: str
    carrier: str
    status: str
    events: list[TrackingEventOut]
