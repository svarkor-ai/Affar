"""PurchaseOrder + PurchaseOrderLine aggregates (contract C18).

C18: unit_cost is PO-scoped (a negotiated per-supplier cost) and is wire-supplied —
but strictly bounded server-side (ge=0, Decimal(12,2)); line_total is recomputed
server-side. Purchase-side totals never feed invoice reconciliation (C16).
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

PO_STATUS: tuple[str, ...] = ("draft", "ordered", "received")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )

    supplier: Mapped["Supplier"] = relationship(
        "Supplier", back_populates="purchase_orders"
    )
    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        "PurchaseOrderLine",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderLine.id",
    )

    def __repr__(self) -> str:
        return f"<PurchaseOrder(id={self.id}, status={self.status!r})>"


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    purchase_order: Mapped["PurchaseOrder"] = relationship(
        "PurchaseOrder", back_populates="lines"
    )
    item: Mapped["Item"] = relationship("Item")

    def __repr__(self) -> str:
        return f"<PurchaseOrderLine(id={self.id}, po_id={self.po_id})>"
