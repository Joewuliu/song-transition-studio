"""Small, centralized runtime configuration.

Covers the set of frontend origins allowed to call this API (CORS) and
the per-file upload size limit. Kept separate from main.py/
upload_validation.py so it's importable/testable on its own, without
spinning up the FastAPI app.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

# --- CORS ------------------------------------------------------------------

# Safe default for local development: only the frontend's default dev
# port. Deliberately never a wildcard ("*") — CORSMiddleware is
# configured with allow_credentials=True, and the CORS spec disallows
# combining a wildcard allow-origin with credentials anyway (browsers
# reject it outright); get_allowed_origins() below also actively refuses
# to pass "*" through even if someone sets it in FRONTEND_ORIGINS.
DEFAULT_FRONTEND_ORIGIN = "http://localhost:3000"

# Comma-separated list of origins allowed to call this API, e.g.
# "https://app.example.com,https://staging.example.com" for a deployed
# frontend. Unset (or empty/whitespace-only, or entirely malformed) falls
# back to DEFAULT_FRONTEND_ORIGIN, so local development works with zero
# setup.
FRONTEND_ORIGINS_ENV_VAR = "FRONTEND_ORIGINS"

# A browser Origin is exactly scheme://host[:port] — no path, no trailing
# slash, no wildcard. Anything else is almost certainly a copy-paste
# mistake (a full URL with a path, a trailing "/", "*", ...) and is
# rejected rather than silently passed to CORSMiddleware.
_ORIGIN_PATTERN = re.compile(r"^https?://[^\s/]+$")


def _is_valid_origin(origin: str) -> bool:
    return bool(_ORIGIN_PATTERN.match(origin))


def get_allowed_origins() -> list[str]:
    """The origin list CORSMiddleware should allow.

    Reads FRONTEND_ORIGINS as a comma-separated list; whitespace around
    each entry is stripped, empty entries are dropped, and any entry that
    doesn't look like a bare "scheme://host[:port]" origin (including a
    literal "*") is dropped with a logged warning rather than passed
    through. Falls back to [DEFAULT_FRONTEND_ORIGIN] when nothing usable
    remains.
    """
    raw = os.environ.get(FRONTEND_ORIGINS_ENV_VAR, "")
    candidates = [origin.strip() for origin in raw.split(",") if origin.strip()]

    origins = []
    for candidate in candidates:
        if _is_valid_origin(candidate):
            origins.append(candidate)
        else:
            logger.warning(
                "Ignoring malformed %s entry %r (expected e.g. "
                "https://example.com — no path, no trailing slash, no wildcard)",
                FRONTEND_ORIGINS_ENV_VAR,
                candidate,
            )

    return origins or [DEFAULT_FRONTEND_ORIGIN]


# --- Upload limits -----------------------------------------------------------

# Generous for a single local track; deliberately not raised further by
# default since /transitions/render accepts TWO such uploads in one
# request (see upload_validation.py), so worst-case per-request memory is
# roughly 2x this figure even before decoding.
DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB

# Lets an operator tighten (or, with care, raise) the per-file limit
# without a code change, e.g. on a host with less available memory.
MAX_UPLOAD_BYTES_ENV_VAR = "MAX_UPLOAD_BYTES"


def get_max_upload_bytes() -> int:
    """The maximum size, in bytes, accepted for a single uploaded audio
    file. Falls back to DEFAULT_MAX_UPLOAD_BYTES when MAX_UPLOAD_BYTES is
    unset or not a positive integer."""
    raw = os.environ.get(MAX_UPLOAD_BYTES_ENV_VAR)
    if raw is None:
        return DEFAULT_MAX_UPLOAD_BYTES
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "Ignoring non-integer %s=%r; using the default of %d bytes",
            MAX_UPLOAD_BYTES_ENV_VAR,
            raw,
            DEFAULT_MAX_UPLOAD_BYTES,
        )
        return DEFAULT_MAX_UPLOAD_BYTES
    if value <= 0:
        logger.warning(
            "Ignoring non-positive %s=%r; using the default of %d bytes",
            MAX_UPLOAD_BYTES_ENV_VAR,
            raw,
            DEFAULT_MAX_UPLOAD_BYTES,
        )
        return DEFAULT_MAX_UPLOAD_BYTES
    return value
