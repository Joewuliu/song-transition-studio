# Song Transition Studio

Song Transition Studio is a web app that builds smooth, beat-aligned
transitions between two songs. Load two local audio files, let it analyze
their tempo, beat grid, and key; get a few different deterministic
transition techniques to audition side by side (or pick your own anchor
points by hand); fine-tune the result; and export exactly the rendered
clip you listened to as a WAV file.

It's interesting as a project because the transition logic is a real,
from-scratch DSP and music-analysis pipeline — beat tracking, phase-vocoder
time-stretching, chroma-based key estimation, harmonic-compatibility
scoring, structural-change detection — rather than a thin wrapper around
someone else's audio library, with a frontend and backend that share one
`TransitionPlan` representation end to end so "suggested," "hand-edited,"
and "what you're about to export" are never three different things.

**Main workflow:** add two tracks → analyze → choose (or hand-pick) a
transition → fine-tune → generate a preview → export the WAV.

**Core architecture:** a Next.js/TypeScript frontend talking to a
stateless FastAPI/Python backend (`librosa` + `numpy`/`scipy` for
analysis and rendering) over a small typed HTTP client — no database, no
accounts, no persisted audio.

<!-- Add screenshots or a demo link/GIF here once available. -->

## Features

- Drag-and-drop (or click-to-browse) upload for two local audio tracks;
  nothing is sent anywhere until you explicitly analyze, preview, or
  export.
- Tempo/beat-grid detection, an estimated musical key, and a ranked
  shortlist of good transition entry/exit beats per track.
- One-click "Find transitions": a deterministic base suggestion (anchor
  pair, tempo interpretation, starting gains) plus three ready-to-audition
  variants derived from it — Smooth Blend, Bass Swap, and Quick Mix —
  each independently previewable before you commit to one.
- Fully manual alternative: click the waveform or step beat-by-beat to
  choose anchors yourself, no suggestion required.
- A hand-editable transition plan: length, per-track gain trim, blend
  timing, Smooth vs. Bass Swap style, and bass-swap timing/width.
- A real rendered preview player with explicit "stale" tracking — if you
  change a setting after generating a preview, the UI tells you so rather
  than letting an old render pass as current.
- Export downloads exactly the audio you just previewed, with an
  auto-generated (and editable) filename.

## Architecture

Monorepo with two apps:

- **`apps/web`** — Next.js (App Router) + TypeScript + Tailwind CSS +
  WaveSurfer.js. Holds the authoritative `TransitionPlan` state and talks
  to the backend through a small typed HTTP client (`src/lib/api.ts`),
  configured entirely by `NEXT_PUBLIC_API_URL`.
- **`apps/api`** — FastAPI + Python. Stateless: every request carries
  whatever audio/analysis it needs; uploaded audio is decoded into a
  private temp file, processed, and deleted before the response is sent
  — nothing is stored between requests. Uses `librosa`/`numpy`/`scipy`
  for analysis and rendering, `soundfile` for WAV I/O.

Design boundaries the codebase keeps deliberately clean:

- Audio processing (backend) is separate from UI code (frontend).
- Automatic transition planning (`transition_planner.py`) is separate
  from audio rendering (`transition_renderer.py`) — planning only ever
  produces a `TransitionPlan`-shaped suggestion; rendering is the one
  place that actually does DSP, reused by every transition style and by
  manual edits alike.
- The manual editor and the automatic suggestion flow operate on the
  exact same `TransitionPlan` representation — adopting a suggested
  variant just replaces the plan's field values, nothing more.

The transition-suggestion system is a deterministic music-analysis
pipeline (tempo/beat detection, chroma-based key estimation, harmonic
compatibility scoring, structural-change and candidate ranking) — not a
machine-learning or generative model. The same two analyses always
produce the same suggestion.

## How it works

1. **Add tracks** — load Song A and Song B.
2. **Analyze** — each track is sent to the backend once, to detect tempo,
   beats, key, and candidate transition points.
3. **Choose a transition** — click "Find transitions" for three ready-made
   options (Smooth Blend / Bass Swap / Quick Mix) and preview them
   individually, or skip straight to picking anchor points by hand on
   each waveform.
4. **Fine-tune** — once anchors are set (from a suggestion or manually),
   adjust transition length, gain, blend timing, style, and bass-swap
   parameters.
5. **Generate a preview** — renders the actual transition audio so you
   can listen before exporting; any further edit marks that preview
   stale, so you always hear the current settings before exporting them.
6. **Export** — downloads exactly the rendered preview, as a `.wav` file.

Export downloads the transition **clip only** — the beat-aligned
crossfade region around the two chosen anchors, at the configured
transition length. It never exports either song in full, and never
stitches "all of Song A into all of Song B."

## Prerequisites

- **Backend:** Python 3.14+ and [uv](https://docs.astral.sh/uv/).
- **Frontend:** Node.js 20+ and npm.

(Versions above reflect `apps/api/pyproject.toml`'s `requires-python` and
`apps/web`'s `@types/node` target — there's no stricter enforced minimum
beyond that.)

## Local setup

Clone the repo, then set up each app independently.

### Backend

```bash
cd apps/api
uv sync
cp .env.example .env   # optional for local dev — see Environment variables below
uv run fastapi dev app/main.py
```

The API listens on `http://localhost:8000` by default. Visit
`http://localhost:8000/health` to confirm it's running.

### Frontend

```bash
cd apps/web
npm install
cp .env.local.example .env.local
npm run dev
```

The app runs on `http://localhost:3000`.

With both running, open `http://localhost:3000`, add two audio files, and
work through the flow described above.

## Environment variables

### `apps/web/.env.local`

| Variable              | Purpose                                  | Local default            |
| ---------------------- | ------------------------------------------ | -------------------------- |
| `NEXT_PUBLIC_API_URL` | Base URL the frontend calls for the API. | `http://localhost:8000`  |

### `apps/api/.env`

| Variable            | Purpose                                             | Local default            |
| --------------------- | ------------------------------------------------------ | --------------------------- |
| `FRONTEND_ORIGINS`  | Comma-separated list of origins allowed via CORS.   | `http://localhost:3000`  |
| `MAX_UPLOAD_BYTES`  | Max size (bytes) accepted per uploaded audio file.  | `104857600` (100 MB)     |

Both backend variables are optional for local development. For a
deployed frontend, set `FRONTEND_ORIGINS` to that frontend's real
origin(s), e.g. `FRONTEND_ORIGINS=https://your-frontend.example.com`
(comma-separate multiple). It is never safe to set this to `"*"` — the
API is served with credentials enabled, a wildcard origin combined with
credentials is rejected by browsers anyway, and the backend actively
drops any configured entry that isn't a bare `scheme://host[:port]`
origin (logging a warning) rather than passing it through.

`/transitions/render` accepts two files in one request, so peak
per-request upload memory is roughly `2 × MAX_UPLOAD_BYTES` before
decoding begins.

Neither app currently requires any secret values.

## Tests

### Backend (`apps/api`)

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python -m compileall app tests
```

### Frontend (`apps/web`)

```bash
npm run lint
npm run build
```

The frontend currently has no automated test suite (no Jest/Vitest, by
design) — `lint` and `build` (which runs the TypeScript compiler) are the
checks that must pass.

## Deployment notes

The two apps deploy independently — this is intentionally **not** one
combined serverless app. Nothing below is provider-specific beyond the
optional `apps/api/Dockerfile`.

### Frontend (`apps/web`)

1. Deploy `apps/web` to Vercel or any standard Next.js host (`next build`
   / `next start`, or that host's native Next.js support).
2. Set `NEXT_PUBLIC_API_URL` to the backend's HTTPS URL in that host's
   environment configuration.

### Backend (`apps/api`)

1. Deploy `apps/api` as a **persistent** Python web service/container —
   not a serverless function — on something like Render, Railway,
   Fly.io, or an equivalent host. An optional `Dockerfile` is included
   for container-based platforms (see below); it isn't required for
   platforms with native Python/uv support.
2. Set `FRONTEND_ORIGINS` to the deployed frontend's HTTPS origin.
3. Expose whatever port the platform assigns (commonly via a `$PORT`
   environment variable) and run a production ASGI command against it,
   e.g.:

   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
   ```

   Do not assume port 8000 in production — bind to `0.0.0.0` and
   whatever port the platform actually gives you.
4. Give the service enough memory/CPU for `librosa`/`scipy` audio work,
   and a request timeout generous enough for it — analysis and rendering
   are synchronous, CPU-heavy operations that commonly take several
   seconds per request (longer for longer tracks), not milliseconds.
   Analysis/rendering work runs off the asyncio event loop (via a worker
   thread) so one long request doesn't stall other concurrent requests
   like `/health`, but there is no background job queue: a request that
   exceeds the platform's timeout will simply fail, and a burst of
   concurrent renders is bounded by CPU, not by a queue — fine for a
   small demo, not a substitute for real job infrastructure.

### Optional container build

```bash
cd apps/api
docker build -t song-transition-api .
docker run -p 8000:8000 -e FRONTEND_ORIGINS=https://your-frontend.example.com song-transition-api
```

## Limitations

- Backend processing is entirely stateless and in-memory/temp-file per
  request — there is no persistent storage, accounts, or history, and
  nothing is saved server-side.
- No background job queue (no Celery/Redis/etc.): every analyze/preview/
  export call is a synchronous, CPU-heavy request-response cycle, offloaded
  to a worker thread so it doesn't block other requests, but still bounded
  by the host's CPU and its request timeout. This is appropriate for a
  small personal/demo deployment, not for concurrent heavy production
  traffic.
- Every preview or export render re-uploads both full source files to the
  backend; there's no server-side audio cache between requests.
- The renderer only reads a short window of each source track around its
  chosen anchor, so transitions are limited to the supported 8/16/32-beat
  lengths.
- Key estimation and harmonic-compatibility scoring are heuristic
  (chroma-based Krumhansl-Schmuckler key finding) and report unknown/
  neutral results when a track's tonal content is ambiguous, rather than
  guessing.
- Time-stretching is phase-vocoder based and works best for modest tempo
  differences; large tempo gaps beyond the supported half/double-time
  correction can sound artifacted.
- There is no undo/redo in the manual editor beyond the "Reset mix
  settings" action.
