"""Customer wire schemas (C9 + C23).

One Pydantic model set for the customer aggregate. No monetary field on the
wire — a customer record here is contact/master data (matching the Customer
ORM, contract C9). Routers return schema objects, never raw ORM objects.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CustomerIn(BaseModel):
    """POST/PUT /api/customers body (C9)."""

    name: str = Field(min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)
    address: Optional[str] = Field(default=None, max_length=500)


class CustomerOut(BaseModel):
    """Customer representation on the wire — never a raw ORM object."""

    id: int
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    created_at: datetime
