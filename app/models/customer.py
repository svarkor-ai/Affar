"""Customer aggregate (contract C9)."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # MC 1349.2 (F4): Swedish company registration number (organisationsnummer).
    org_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # MC 1175.5: deactivation, not deletion (mirrors User.is_active 1120.1 and
    # Item.active C7). Past orders/invoices keep pointing at the record.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )

    # Demo only (I4). Relationship used by GET /api/customers/{id} (with_orders).
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="customer")

    def __repr__(self) -> str:
        return f"<Customer(id={self.id}, name={self.name!r})>"
