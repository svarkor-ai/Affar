"""Tests for MC 1175.4 — purchase rättbara: PATCH rader/kostnad (Ordered) + cancel.

Surface added by this card:
  PATCH /api/purchase-orders/{id}          PurchaseOrderPatch -> POut (drafts)
  PATCH /api/purchase-orders/{id}/status   + "cancel" (makulering, terminal)

Rules under test (mirrors T1/T2 sales-side rules on the buy side):
  * Draft lines are replaceable incl. unit_cost (C18); line_total recomputed
    server-side; a replaced draft keeps server-owned money math.
  * ordered is NOT editable (409); cancelled is NOT editable (410, terminal).
  * cancel: draft/ordered -> cancelled (terminal). received -> 409 (stock is
    already in). Re-cancel -> 409. Any lifecycle move on a cancelled PO -> 410.
  * draft -> ordered still works through the status PATCH (routed through the
    makulering-aware purchase_edit.set_ordered) and stock never moves until
    "received" (I2).
  * Guards: unknown item 404 (atomic rollback), extra keys 422
    (extra="forbid"), negative unit_cost 422, sales role 403.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

import app.config as _cfg

_cfg.SECRET_KEY = "test-secret-not-for-prod-0123456789abcdef"
_cfg.JWT_ALGORITHM = "HS256"
_cfg.ACCESS_TOKEN_EXPIRE_MINUTES = 60

from app.database import get_engine, init_db  # noqa: E402
from app.auth import create_access_token  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Item, Supplier  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


def _hdr(role="admin", uid=1):
    return {"Authorization": f"Bearer {create_access_token(uid, role)}"}


def _seed(client):
    """Seed supplier + two items; return their ids (direct DB — fixtures, not surface)."""
    init_db()
    with Session(get_engine()) as s:
        sup = Supplier(name="Lev AB")
        it1 = Item(sku="K-1", name="Komponent 1", unit_price=Decimal("10.00"),
                   qty_on_hand=5, active=True)
        it2 = Item(sku="K-2", name="Komponent 2", unit_price=Decimal("20.00"),
                   qty_on_hand=5, active=True)
        s.add_all([sup, it1, it2])
        s.commit()
        return sup.id, it1.id, it2.id


def _make_po(client, supplier_id, item_id, qty=2, unit_cost="50.00"):
    r = client.post(
        "/api/purchase-orders",
        json={"supplier_id": supplier_id,
              "lines": [{"item_id": item_id, "qty": qty, "unit_cost": unit_cost}]},
        headers=_hdr(),
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_draft_po_lines_replaceable_costs_recomputed(client):
    sid, i1, i2 = _seed(client)
    po = _make_po(client, sid, i1, qty=2, unit_cost="50.00")
    assert po["status"] == "draft"
    assert Decimal(po["lines"][0]["line_total"]) == Decimal("100.00")

    r = client.patch(
        f"/api/purchase-orders/{po['id']}",
        json={"lines": [
            {"item_id": i1, "qty": 1, "unit_cost": "55.00"},
            {"item_id": i2, "qty": 3, "unit_cost": "7.50"},
        ]},
        headers=_hdr("procurement"),
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert [ln["item_id"] for ln in out["lines"]] == [i1, i2]
    assert Decimal(out["lines"][0]["line_total"]) == Decimal("55.00")
    assert Decimal(out["lines"][1]["line_total"]) == Decimal("22.50")


def test_stock_untouched_until_received(client):
    sid, i1, _ = _seed(client)
    po = _make_po(client, sid, i1, qty=4, unit_cost="10.00")
    pid = po["id"]
    client.patch(f"/api/purchase-orders/{pid}",
                 json={"lines": [{"item_id": i1, "qty": 6, "unit_cost": "10.00"}]},
                 headers=_hdr())
    r = client.patch(f"/api/purchase-orders/{pid}/status",
                     json={"status": "ordered"}, headers=_hdr())
    assert r.status_code == 200 and r.json()["status"] == "ordered"
    with Session(get_engine()) as s:
        assert s.get(Item, i1).qty_on_hand == 5  # ordered moved no stock (I2)
    r = client.patch(f"/api/purchase-orders/{pid}/status",
                     json={"status": "received"}, headers=_hdr())
    assert r.status_code == 200 and r.json()["status"] == "received"
    with Session(get_engine()) as s:
        assert s.get(Item, i1).qty_on_hand == 11  # stock-in on received only


def test_ordered_po_not_editable(client):
    sid, i1, _ = _seed(client)
    po = _make_po(client, sid, i1)
    client.patch(f"/api/purchase-orders/{po['id']}/status",
                 json={"status": "ordered"}, headers=_hdr())
    r = client.patch(f"/api/purchase-orders/{po['id']}",
                     json={"lines": [{"item_id": i1, "qty": 9, "unit_cost": "1.00"}]},
                     headers=_hdr())
    assert r.status_code == 409


def test_cancel_draft_and_ordered(client):
    sid, i1, _ = _seed(client)
    po = _make_po(client, sid, i1)
    r = client.patch(f"/api/purchase-orders/{po['id']}/status",
                     json={"status": "cancel"}, headers=_hdr())
    assert r.status_code == 200 and r.json()["status"] == "cancelled"

    po2 = _make_po(client, sid, i1)
    client.patch(f"/api/purchase-orders/{po2['id']}/status",
                 json={"status": "ordered"}, headers=_hdr())
    r = client.patch(f"/api/purchase-orders/{po2['id']}/status",
                     json={"status": "cancel"}, headers=_hdr())
    assert r.status_code == 200 and r.json()["status"] == "cancelled"


def test_cancelled_is_terminal(client):
    sid, i1, _ = _seed(client)
    po = _make_po(client, sid, i1)
    pid = po["id"]
    client.patch(f"/api/purchase-orders/{pid}/status",
                 json={"status": "cancel"}, headers=_hdr())
    # re-cancel -> 409
    r = client.patch(f"/api/purchase-orders/{pid}/status",
                     json={"status": "cancel"}, headers=_hdr())
    assert r.status_code == 409
    # lifecycle re-entry (ordered/received/draft) -> 410
    for st in ("ordered", "received", "draft"):
        r = client.patch(f"/api/purchase-orders/{pid}/status",
                         json={"status": st}, headers=_hdr())
        assert r.status_code == 410, (st, r.text)
    # edit -> 410
    r = client.patch(f"/api/purchase-orders/{pid}",
                     json={"lines": [{"item_id": i1, "qty": 1, "unit_cost": "1.00"}]},
                     headers=_hdr())
    assert r.status_code == 410


def test_received_po_cannot_be_cancelled(client):
    sid, i1, _ = _seed(client)
    po = _make_po(client, sid, i1)
    pid = po["id"]
    client.patch(f"/api/purchase-orders/{pid}/status",
                 json={"status": "ordered"}, headers=_hdr())
    client.patch(f"/api/purchase-orders/{pid}/status",
                 json={"status": "received"}, headers=_hdr())
    r = client.patch(f"/api/purchase-orders/{pid}/status",
                     json={"status": "cancel"}, headers=_hdr())
    assert r.status_code == 409


def test_edit_guards(client):
    sid, i1, _ = _seed(client)
    po = _make_po(client, sid, i1)
    pid = po["id"]
    # unknown item -> 404, and the draft keeps its ORIGINAL single line
    r = client.patch(f"/api/purchase-orders/{pid}",
                     json={"lines": [{"item_id": 9999, "qty": 1, "unit_cost": "1.00"}]},
                     headers=_hdr())
    assert r.status_code == 404
    assert len(client.get(f"/api/purchase-orders/{pid}", headers=_hdr()).json()["lines"]) == 1
    # negative cost -> 422 (schema bound)
    r = client.patch(f"/api/purchase-orders/{pid}",
                     json={"lines": [{"item_id": i1, "qty": 1, "unit_cost": "-1.00"}]},
                     headers=_hdr())
    assert r.status_code == 422
    # smuggled extra key -> 422 (extra="forbid")
    r = client.patch(f"/api/purchase-orders/{pid}",
                     json={"lines": [{"item_id": i1, "qty": 1, "unit_cost": "1.00",
                                      "status": "received"}]},
                     headers=_hdr())
    assert r.status_code == 422
    # unknown PO -> 404
    r = client.patch("/api/purchase-orders/9999",
                     json={"lines": [{"item_id": i1, "qty": 1, "unit_cost": "1.00"}]},
                     headers=_hdr())
    assert r.status_code == 404


def test_role_gating(client):
    sid, i1, _ = _seed(client)
    po = _make_po(client, sid, i1)
    r = client.patch(f"/api/purchase-orders/{po['id']}",
                     json={"lines": [{"item_id": i1, "qty": 1, "unit_cost": "1.00"}]},
                     headers=_hdr("sales"))
    assert r.status_code == 403
    r = client.patch(f"/api/purchase-orders/{po['id']}/status",
                     json={"status": "cancel"}, headers=_hdr("sales"))
    assert r.status_code == 403
    r = client.patch(f"/api/purchase-orders/{po['id']}/status",
                     json={"status": "cancel"})
    assert r.status_code == 401
