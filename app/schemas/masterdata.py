"""Master-data activation schemas (MC 1175.5).

One tiny shared body for the three deactivation surfaces (items, customers,
suppliers): ``PATCH /api/{resource}/{id}/active``. Deliberately its own module
(the repo has no common.py to extend — C23 style keeps schemas per wire
concern) so the three routers share ONE wire contract instead of three copies.

``extra="forbid"`` (1175.1 pattern): a client can never smuggle a name, price
or any other field through an activation PATCH — only ``is_active``.
"""

from pydantic import BaseModel, ConfigDict


class ActivePatch(BaseModel):
    """PATCH .../active body — set the activation flag (deactivation card)."""

    model_config = ConfigDict(extra="forbid")

    is_active: bool
