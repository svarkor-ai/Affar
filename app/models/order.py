"""Order + OrderLine aggregates (contract C13, rev-2).

C13 rev-2: OrderLine.unit_price is a server-side SNAPSHOT of Item.unit_price taken
at order creation — the wire carries only {item_id, qty}. orders.id is the sequential
internal PK; tracking_ref is a staff-only human label. Neither reaches a public route.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

ORDER_STATUS: tuple[str, ...] = ("draft", "confirmed", "shipped", "delivered")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # STAFF-ONLY human ref (e.g. "ORD-<id>"). Never the public lookup key (rev-2, C20).
    tracking_ref: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    customer: Mapped["Customer"] = relationship("Customer", back_populates="orders")
    lines: Mapped[list["OrderLine"]] = relationship(
        "OrderLine",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderLine.id",
    )

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, status={self.status!r})>"


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    # SNAPSHOT of Item.unit_price taken server-side at order creation (C14, rev-2).
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Computed qty * unit_price from server-set values only (never client-supplied).
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="lines")
    item: Mapped["Item"] = relationship("Item")

    def __repr__(self) -> str:
        return f"<OrderLine(id={self.id}, item_id={self.item_id}, qty={self.qty})>"
