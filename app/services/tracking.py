"""Tracking service (contract C20 rev-3 / C21 rev-3).

Owns the lookup, sanitisation and WRITE rules for the delivery-tracking surface:

  * A delivery track is resolved ONLY by the generated, non-sequential,
    high-entropy ``tracking_id`` (invariant I5) - never by ``order_id`` and
    never by the staff-only ``tracking_ref``.
  * An unknown/forged tracking_id raises 404 without revealing whether a track
    exists (a uniform 404 does not let an attacker enumerate tracks).
  * The public timeline returns each event's ``status`` + ``at``. The staff-only
    ``note`` is read but deliberately never surfaced (C21 rev-2) - the public
    representation is built from only public fields.
"""

from datetime import UTC, datetime
from secrets import token_hex

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import DeliveryTrack, TrackingEvent, TRACK_EVENT


def get_track_by_public_id_or_404(db: Session, tracking_id: str) -> DeliveryTrack:
    """Return the track for the public ``tracking_id`` or raise 404.

    The lookup is keyed ONLY on the generated public key (I5). A 404 here is
    indistinguishable for a caller between "no such tracking" and "no such
    order" - the internal order id is never a valid lookup key, so passing it
    yields the same uniform 404.
    """
    track = db.query(DeliveryTrack).filter(
        DeliveryTrack.tracking_id == tracking_id
    ).first()
    if track is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tracking not found",
        )
    return track


def ordered_public_events(db: Session, track: DeliveryTrack) -> list[dict]:
    """Return the track's events, chronological, stripped of staff fields.

    Each returned dict carries ONLY the public keys ``status`` and ``at`` -
    the ORM's ``note`` is never copied across, so no staff free text can reach
    the wire (C21 rev-2).
    """
    events = (
        db.query(TrackingEvent)
        .filter(TrackingEvent.delivery_track_id == track.id)
        .order_by(TrackingEvent.at.asc())
        .all()
    )
    return [{"status": e.status, "at": e.at} for e in events]


# ---------------------------------------------------------------------------
# WRITE side (contract C21 rev-3 / MC 695.1)
# ---------------------------------------------------------------------------


def create_track_for_order(db: Session, order_id: int) -> DeliveryTrack:
    """Create a DeliveryTrack + a first 'placed' event for *order_id*.

    Called once from order confirmation so every confirmed order gets
    "DeliveryTrack + event" immediately (C21). Idempotent: order_id is UNIQUE
    on delivery_tracks, so if a track already exists it is returned unchanged
    (never a second track for one order). The public tracking_id is generated
    here as high-entropy hex (secrets.token_hex(16)) and is never the
    incremental order id (I5). No commit here — the caller commits so the track
    is created in the same transaction as the confirm.
    """
    existing = (
        db.query(DeliveryTrack)
        .filter(DeliveryTrack.order_id == order_id)
        .first()
    )
    if existing is not None:
        return existing

    track = DeliveryTrack(
        order_id=order_id,
        tracking_id=token_hex(16),
    )
    db.add(track)
    db.flush()
    db.add(
        TrackingEvent(
            delivery_track_id=track.id,
            status="placed",
            note="Ordern är mottagen och bekräftad.",
        )
    )
    return track


def append_track_event(
    db: Session, track: DeliveryTrack, status_name: str, note: str | None = None
) -> DeliveryTrack:
    """Append one TrackingEvent to *track*, returning the (updated) track.

    *status_name* must be a member of the closed TRACK_EVENT set; the caller's
    schema validation already rejected anything else, this is a defensive
    double-check. The staff *note* is stored on the ORM row only — it never
    appears on the public DeliveryTrackOut projection. No commit here; the
    router commits.
    """
    if status_name not in TRACK_EVENT:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"status must be one of {list(TRACK_EVENT)}",
        )

    db.add(
        TrackingEvent(
            delivery_track_id=track.id,
            status=status_name,
            note=note,
            at=datetime.now(UTC),
        )
    )
    db.flush()
    return track
