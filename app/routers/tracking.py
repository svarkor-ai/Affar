"""Public tracking router (contract C20 rev-3 / C21 rev-2).

The "publik spårning" surface: a customer follows their delivery by the
generated, non-sequential ``tracking_id`` WITHOUT logging in. The route mounts
NO auth dependency - that is the defining property of this card (contrast the
staff-only internal surfaces, which use ``require_role``).

Surface:
  GET /api/tracking/{tracking_id}   DeliveryTrackOut   (public, no auth)

Security properties enforced at the schema/service layer and guaranteed by this
router's test file:
  * keyed ONLY by tracking_id (never order id / tracking_ref),
  * staff ``note`` and internal ids never emitted,
  * unknown tracking_id -> uniform 404.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_session
from app.schemas.tracking import DeliveryTrackOut, TrackingEventIn, TrackingEventOut
from app.services import tracking as svc

router = APIRouter(prefix="/api/tracking", tags=["tracking"])

# Staff who may advance a delivery. Mirror the internal sales surfaces - the
# customer role is read-only on tracking (public GET).
STAFF_ROLES = ["admin", "sales", "finance"]


@router.get("/{tracking_id}", response_model=DeliveryTrackOut)
def public_track(tracking_id: str, db: Session = Depends(get_session)) -> DeliveryTrackOut:
    """Resolve a delivery track by its public tracking_id.

    Public: no authentication is required (C20 - "publik spårning"). The staff
    note and any internal id are never returned; the schema only exposes the
    public timeline (status + at) and the carrier.
    """
    track = svc.get_track_by_public_id_or_404(db, tracking_id)
    events = svc.ordered_public_events(db, track)

    return DeliveryTrackOut(
        tracking_id=track.tracking_id,
        carrier=track.carrier,
        status=events[-1]["status"] if events else "no-events",
        events=[TrackingEventOut(**e) for e in events],
    )


@router.post(
    "/{tracking_id}/events",
    response_model=DeliveryTrackOut,
    status_code=201,
)
def append_event(
    tracking_id: str,
    body: TrackingEventIn,
    db: Session = Depends(get_session),
    _staff: dict = Depends(require_role(STAFF_ROLES)),
) -> DeliveryTrackOut:
    """Append one tracking event to a delivery (staff WRITE surface, C21 rev-3).

    Restricted to admin/sales/finance (the roles who manage deliveries). The
    body carries a closed-set ``status`` plus an optional staff ``note``. The
    note is stored internally but the response is the SAME public
    ``DeliveryTrackOut`` projection, so no staff note can reach the caller.
    Unknown tracking_id -> uniform 404.
    """
    track = svc.get_track_by_public_id_or_404(db, tracking_id)
    body.validate_status()
    svc.append_track_event(db, track, body.status, body.note)
    db.commit()

    events = svc.ordered_public_events(db, track)
    return DeliveryTrackOut(
        tracking_id=track.tracking_id,
        carrier=track.carrier,
        status=events[-1]["status"] if events else "no-events",
        events=[TrackingEventOut(**e) for e in events],
    )
