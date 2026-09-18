# Optional production image for the backend (apps/api).
#
# Local development does NOT need Docker — keep using
# `uv run fastapi dev app/main.py` directly. This is deployment support
# for hosts that run a container (Render, Railway, Fly.io, etc.), not a
# requirement.
#
# Build (from apps/api):
#   docker build -t song-transition-api .
# Run:
#   docker run -p 8000:8000 -e FRONTEND_ORIGINS=https://your-frontend.example.com song-transition-api
#
# The platform's assigned port is read from $PORT at container start (see
# CMD below) — most container platforms inject this automatically.

FROM python:3.14-slim

# soundfile's PyPI wheel bundles libsndfile on most platforms, but
# installing the system package too is cheap insurance against a
# "works locally, fails in the container" audio-decode surprise.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# uv's own published image ships a static, self-contained binary — this
# just copies it in rather than installing uv via pip.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Dependency metadata first, so this (slow) layer is cached independently
# of application source changes below it.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY app ./app
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:${PATH}"

# Uploaded audio is decoded from a request body into the OS temp
# directory and removed again before the response is sent (see
# services/audio_analysis.py and services/transition_renderer.py) — never
# written anywhere under /app, and never baked into this image.

# Default for local `docker run`; real deployments should set the actual
# assigned port via -e PORT=... or the platform's own env injection.
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
