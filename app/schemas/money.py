"""Shared comma-decimal normaliser for wire-supplied money fields (C23).

MC 1182.6: the UI invites Swedish users to type "10,50" (placeholder
"0,00"), but pydantic's Decimal parser only accepts '.' as the decimal
separator — the API answered 422 "Input should be a valid decimal". The
backend is the authority on money (C23), so the fix lives HERE, on the
wire boundary, not in the client.

``comma_to_dot`` runs BEFORE pydantic parses the field (mode="before") and
rewrites the STRING form only — numbers pass through untouched. When both
separators are present the LAST one is the decimal separator, so
"1.234,50" and "1,234.50" both parse to 1234.50. Empty/whitespace strings
are left for pydantic to reject with its own message. All C23 bounds
(ge=0 / gt=0, max_digits=12, decimal_places=2) are enforced AFTER
normalisation, exactly as before.
"""

from pydantic import field_validator


def comma_to_dot(x):
    """Normalise a Swedish comma decimal string to a dot-decimal string."""
    if isinstance(x, str):
        s = x.strip().replace(" ", "")
        if s and ("," in s or "." in s):
            if "," in s and "." in s:
                if s.rfind(",") > s.rfind("."):
                    s = s.replace(".", "").replace(",", ".")
                else:
                    s = s.replace(",", "")
            else:
                s = s.replace(",", ".")
        return s
    return x


def money_comma_validator(*field_names):
    """Build a mode="before" validator accepting comma decimals on the wire.

    ``check_fields=False`` lets one shared validator serve several schema
    classes whose money field is named unit_price, unit_cost or amount.
    """

    @field_validator(*field_names, mode="before", check_fields=False)
    @classmethod
    def _accept_comma_decimals(cls, v):
        return comma_to_dot(v)

    return _accept_comma_decimals
