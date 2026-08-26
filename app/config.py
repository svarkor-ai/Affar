"""Configuration — C1 (app/config.py). Env config, hard-fail (I6).

Provider        : teddy, MC 691.1 (R1 — C1-config, SECRET_KEY hard-fail + JWT)
Supersedes      : the thin placeholder config that only defined DATABASE_URL.
Contract        : C1 (architecture rev 1745), invariants I6/I7.

Surface (module-level names the rest of the app imports):
    DATABASE_URL                  env AFFAR_DATABASE_URL,
                                  default "sqlite:///./affar.db"
    SECRET_KEY                    env AFFAR_SECRET_KEY, no fallback,
                                  validate_secret_key() raises RuntimeError
                                  at import if unset / short / known-insecure
    JWT_ALGORITHM                 "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES   int, default 60*24 (24h)
    CORS_ORIGINS                  env AFFAR_CORS_ORIGINS (comma/semicolon-list),
                                  default ["*"] for local dev (read at runtime)
    validate_secret_key(key)->str preserved verbatim from bibliotek (I6).

I6 requires the app to refuse to start (RuntimeError at import) when no
SECRET_KEY is present or the value is forgeable. There is intentionally NO
fallback secret: a hard crash is safer than signing tokens we cannot stand
behind. Operators set AFFAR_SECRET_KEY before starting, e.g.:

    export AFFAR_SECRET_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))')"

Everything is read from the environment at import — the module never inlines
a secret value.
"""

import os

DATABASE_URL = os.getenv("AFFAR_DATABASE_URL", "sqlite:///./affar.db")

# ---------------------------------------------------------------------------
# SECRET_KEY (JWT signing key) — I6 hard-fail, verbatim bibliotek semantics.
#
# The prior placeholder dropped back to nothing and shipped without a key, so
# we must not introduce any fallback here. A usable HS256 signing key must
# come from the environment; anything else must stop the app at import.
# ---------------------------------------------------------------------------

_JWT_KEY_MIN_LENGTH = 24
_KNOWN_INSECURE = {
    "",
    "change-me-in-production",
    "dev-secret-key-change-me",
    "bibliotek-dev-secret",
    "secret",
    "insecure-dev-key",
}


def validate_secret_key(key: str | None) -> str:
    """Return *key* if it is usable as the JWT HS256 signing key.

    Raises
    ------
    RuntimeError
        When *key* is None/empty, shorter than ``_JWT_KEY_MIN_LENGTH``, or a
        known-insecure value. The intent is to fail hard at import so an
        insecure configuration can never silently sign tokens.
    """
    if not key:
        raise RuntimeError(
            "SECRET_KEY is not set. Export a strong SECRET_KEY before "
            "starting the app (see config.py)."
        )
    if key in _KNOWN_INSECURE:
        raise RuntimeError(
            "SECRET_KEY is a known-insecure value that shipped publicly in "
            "repo history and is forgeable as a JWT signing key. Rotate it "
            "to a fresh random value before starting the app."
        )
    if len(key) < _JWT_KEY_MIN_LENGTH:
        raise RuntimeError(
            f"SECRET_KEY is too short ({len(key)} chars < {_JWT_KEY_MIN_LENGTH}). "
            "A short key is forgeable as the HS256 signing key. Use a fresh "
            "random value of at least 24 characters."
        )
    return key


SECRET_KEY = validate_secret_key(os.getenv("AFFAR_SECRET_KEY"))
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24h

# CORS origins for the SPA — read at runtime (test/dev), never a secret.
# Comma/semicolon separated env; default permissive for local development.
_cors_raw = os.getenv("AFFAR_CORS_ORIGINS")
CORS_ORIGINS = (
    [o.strip() for o in _cors_raw.replace(";", ",").split(",") if o.strip()]
    if _cors_raw
    else ["*"]
)
