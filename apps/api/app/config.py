"""Small, centralized runtime configuration.

Currently just the set of frontend origins allowed to call this API
(CORS). Kept separate from main.py so it's importable/testable on its
own, without spinning up the FastAPI app.
"""

import os

# Safe default for local development: only the frontend's default dev
# port. Deliberately never a wildcard ("*") — CORSMiddleware below is
# configured with allow_credentials=True, and the CORS spec disallows
# combining a wildcard allow-origin with credentials anyway.
DEFAULT_FRONTEND_ORIGIN = "http://localhost:3000"

# Comma-separated list of origins allowed to call this API, e.g.
# "https://app.example.com,https://staging.example.com" for a deployed
# frontend. Unset (or empty/whitespace-only) falls back to
# DEFAULT_FRONTEND_ORIGIN, so local development works with zero setup.
FRONTEND_ORIGINS_ENV_VAR = "FRONTEND_ORIGINS"


def get_allowed_origins() -> list[str]:
    """The origin list CORSMiddleware should allow.

    Reads FRONTEND_ORIGINS as a comma-separated list; whitespace around
    each entry is stripped and empty entries are dropped. Falls back to
    [DEFAULT_FRONTEND_ORIGIN] when nothing usable was configured.
    """
    raw = os.environ.get(FRONTEND_ORIGINS_ENV_VAR, "")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or [DEFAULT_FRONTEND_ORIGIN]
