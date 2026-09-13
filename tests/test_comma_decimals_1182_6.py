"""MC 1182.6 — Swedish comma decimals accepted on the money wire.

The Items-form placeholder invites "0,00" (comma), but pydantic's Decimal
parser rejected "10,50" with 422 decimal_parsing. Fix: a shared
mode="before" normaliser (app/schemas/money.py) on every wire-supplied
money field — ItemIn.unit_price, PurchaseOrderLineIn.unit_cost,
PaymentIn.amount. C23 bounds (ge=0 / gt=0, 12,2) are enforced AFTER
normalisation, exactly as before.

Real executed checks:
  1. "10,50" / "0,00" / "1 234,50" / "1.234,50" parse on all three fields.
  2. Dot decimals and numbers still parse (no regression).
  3. Bounds still reject: negative, non-numeric, over-max_digits.
  4. End-to-end: POST /api/items with unit_price "10,50" -> 200, not 422.
"""

from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import create_access_token  # noqa: E402
from app.database import get_engine, init_db  # noqa: E402
from app.models import Item  # noqa: E402
from app.schemas.item import ItemIn  # noqa: E402
from app.schemas.payment import PaymentIn  # noqa: E402
from app.schemas.purchase import PurchaseOrderLineIn  # noqa: E402

COMMA_CASES = [
    ("10,50", Decimal("10.50")),
    ("0,00", Decimal("0.00")),
    ("1 234,50", Decimal("1234.50")),
    ("1.234,50", Decimal("1234.50")),
    ("1,234.50", Decimal("1234.50")),
    ("10.50", Decimal("10.50")),
    (10.5, Decimal("10.5")),
    ("10", Decimal("10")),
]


def test_itemin_accepts_comma_decimals():
    for raw, want in COMMA_CASES:
        assert ItemIn(sku="S", name="N", unit_price=raw).unit_price == want


def test_purchase_line_accepts_comma_decimals():
    for raw, want in COMMA_CASES:
        got = PurchaseOrderLineIn(item_id=1, qty=1, unit_cost=raw).unit_cost
        assert got == want


def test_payment_accepts_comma_decimals():
    for raw, want in COMMA_CASES:
        if want <= 0:  # PaymentIn.amount is gt=0
            continue
        assert PaymentIn(amount=raw, method="bank").amount == want


@pytest.mark.parametrize("bad", ["-0,01", "abc", "", "999999999999,99"])
def test_bounds_still_enforced_after_normalisation(bad):
    with pytest.raises(Exception):
        ItemIn(sku="S", name="N", unit_price=bad)
    with pytest.raises(Exception):
        PurchaseOrderLineIn(item_id=1, qty=1, unit_cost=bad)


# ---------------------------------------------------------------------------
# End-to-end: the exact request the Items form sends
# ---------------------------------------------------------------------------

def _make_app_client() -> TestClient:
    from app.routers.auth import router as auth_router
    from app.routers.items import router as items_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(items_router)
    return TestClient(app)


def test_post_items_comma_decimal_is_200_not_422():
    init_db()
    client = _make_app_client()
    header = {"Authorization": f"Bearer {create_access_token(10, 'admin')}"}
    r = client.post(
        "/api/items",
        headers=header,
        json={"sku": "K1", "name": "Komma test", "unit_price": "10,50", "qty_on_hand": 3},
    )
    assert r.status_code == 200, r.text
    assert r.json()["unit_price"] == "10.50"
    with __import__("sqlalchemy.orm", fromlist=["Session"]).Session(get_engine()) as s:
        row = s.query(Item).filter_by(sku="K1").one()
        assert row.unit_price == Decimal("10.50")
