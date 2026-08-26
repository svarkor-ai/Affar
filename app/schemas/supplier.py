"""Supplier wire schemas (C11/C12 + C23).

One Pydantic model set for the supplier aggregate. C23: no money field here —
the supplier has no monetary attribute on the wire. Routers return schema
objects, never raw ORM objects.
"""

from typing import Optional

from pydantic import BaseModel, Field


class SupplierIn(BaseModel):
    """POST/PUT /api/suppliers body (C12)."""

    name: str = Field(min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=50)
    address: Optional[str] = Field(default=None, max_length=500)
    payment_terms: Optional[str] = Field(default=None, max_length=200)


class SupplierOut(BaseModel):
    """Supplier representation on the wire — never a raw ORM object."""

    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    payment_terms: Optional[str] = None
