"""Public tracking service (contract C20 rev-3 / C21 rev-2).

Owns the lookup and sanitisation rules for the PUBLIC tracking surface:

  * A delivery track is resolved ONLY by the generated, non-sequential,
    high-entropy ``tracking_id`` (invariant I5) - never by ``order_id`` and
    never by the staff-only ``tracking_ref``.
  * An unknown/forged tracking_id raises 404 without revealing whether a track
    exists (a uniform 404 does not let an attacker enumerate tracks).
  * The public timeline returns each event's ``status`` + ``at``. The staff-only
    ``note`` is read but deliberately never surfaced (C21 rev-2) - the public
    representation is built from only public fields.
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import DeliveryTrack


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
    # Local import mirrors app.services.catalog's pattern and avoids any module
    # load-order coupling between the services package and app.models.
    from app.models import TrackingEvent

    events = (
        db.query(TrackingEvent)
        .filter(TrackingEvent.delivery_track_id == track.id)
        .order_by(TrackingEvent.at.asc())
        .all()
    )
    return [{"status": e.status, "at": e.at} for e in events]
