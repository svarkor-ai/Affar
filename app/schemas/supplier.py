"""Supplier wire schemas (C11/C12 + C23).

One Pydantic model set for the supplier aggregate. C23: no money field here —
the supplier has no monetary attribute on the wire. Routers return schema
objects, never raw ORM objects.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SupplierIn(BaseModel):
    """POST/PUT /api/suppliers body (C12).

    ``is_active`` is NOT accepted here (MC 1175.5): activation has its own
    PATCH surface (ActivePatch) — a plain PUT can never flip the flag.
    """

    model_config = ConfigDict(extra="forbid")

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
    # MC 1175.5: deactivation flag (True default = every pre-existing row).
    is_active: bool = True
