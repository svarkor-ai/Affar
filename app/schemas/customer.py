"""Customer wire schemas (C9 + C23).

One Pydantic model set for the customer aggregate. No monetary field on the
wire — a customer record here is contact/master data (matching the Customer
ORM, contract C9). Routers return schema objects, never raw ORM objects.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CustomerIn(BaseModel):
    """POST/PUT /api/customers body (C9).

    ``is_active`` is NOT accepted here (MC 1175.5): the activation flag has
    its own PATCH surface (ActivePatch), so a plain PUT can never silently
    revive or deactivate a customer (1175.1 C14 discipline).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)
    address: Optional[str] = Field(default=None, max_length=500)
    # MC 1349.2 (F4): the frontend sends org_no — accept it on the wire.
    org_no: Optional[str] = Field(default=None, max_length=50)


class CustomerOut(BaseModel):
    """Customer representation on the wire — never a raw ORM object."""

    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    # MC 1349.2 (F4): org_no round-trips to the UI's "Org.nr" column.
    org_no: Optional[str] = None
    # MC 1175.5: deactivation flag (True default = every pre-existing row).
    is_active: bool = True
    created_at: datetime
