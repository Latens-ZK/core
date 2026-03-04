"""
Shared slowapi rate-limiter instance.

Rate-limiting strategy: commitment-hash based, NOT IP-based.

Why: IP-based rate-limiting correlates requests to network identity,
which is a partial privacy leak (same IP seen requesting proofs for
the same Bitcoin commitment). Using the commitment hash as the key
means the limiter only tracks how many proofs a specific commitment
has requested, without identifying the requester by network address.

Limit: max 3 proof requests per commitment per hour.
"""
from slowapi import Limiter
from fastapi import Request


def _get_commitment_from_request(request: Request) -> str:
    """
    Extract the `commitment` field from the JSON request body to use as
    the rate-limit key.

    Falls back to a fixed sentinel string if the body is missing or
    malformed — this keeps Limiter happy while still preventing abuse
    (all malformed requests share one bucket with a low cap).
    """
    # slowapi calls key_func synchronously, but FastAPI has already parsed
    # the body by the time the limiter runs.  We read from request.state
    # where the route sets it, or fall back to a fixed key.
    commitment = getattr(request.state, "commitment_key", None)
    if commitment:
        return str(commitment)
    # Fallback: all un-keyed requests share a very conservative bucket.
    return "no_commitment"


limiter = Limiter(key_func=_get_commitment_from_request)
