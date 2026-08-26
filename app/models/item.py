"""Item aggregate (contract C7) — single source of item truth."""

from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    # Monetary value — DECIMAL(12,2), never float (I7). This is THE only source of a
    # sales line's price; the wire never carries it (rev-2, C14).
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    qty_on_hand: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Item(id={self.id}, sku={self.sku!r}, active={self.active!r})>"
