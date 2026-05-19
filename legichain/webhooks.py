"""Client-side webhook signature verification.

The Legichain platform signs every webhook delivery with HMAC-SHA256 in the
Stripe-compatible format::

    Legichain-Signature: t=1700000000,v1=<hex_digest>

The signed payload is the literal bytes::

    f"{timestamp}.".encode() + body

This module mirrors the server-side signer so that customers can verify
deliveries without depending on the full server package.
"""

from __future__ import annotations

import hashlib
import hmac
import time


def verify_signature(
    payload: bytes,
    header_value: str,
    secret: str,
    *,
    tolerance_sec: int = 300,
) -> bool:
    """Return True iff `header_value` matches an HMAC over `payload`.

    Args:
        payload: Raw request body bytes (do NOT re-serialize the parsed JSON;
                 use the bytes you read off the wire).
        header_value: Contents of the `Legichain-Signature` header
                      (format: `t=<unix>,v1=<hex>`).
        secret: The endpoint secret (visible once when the endpoint was created).
        tolerance_sec: Allowed clock skew. Deliveries older than this window
                       are rejected to thwart replay attacks. Default 5 minutes.

    Returns:
        True on a valid, fresh signature. False otherwise.
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be raw bytes")
    parts = dict(p.split("=", 1) for p in header_value.split(",") if "=" in p)
    try:
        ts = int(parts.get("t", "0"))
        provided = parts.get("v1", "")
    except (ValueError, AttributeError):
        return False
    if not provided or ts <= 0:
        return False
    if abs(time.time() - ts) > tolerance_sec:
        return False
    signed = f"{ts}.".encode() + bytes(payload)
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)
