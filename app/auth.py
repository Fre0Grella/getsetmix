"""Reading a bearer token out of an Authorization header.

Used by the UI's token check (app/main.py) and by the link's per-computer
tokens (app/link.py), so both read the header the same way.
"""
from __future__ import annotations


def bearer_token(header: str) -> str:
    """The token of "Bearer <token>" (the scheme in any case), or "" when the
    header names another scheme or no token."""
    scheme, _, token = (header or "").strip().partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""
