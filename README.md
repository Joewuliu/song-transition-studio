# Song Transition Studio

Song Transition Studio is a web app for building smooth, beat-aligned
transitions between two songs. Load two local audio files, let the app
analyze their tempo and beat structure, choose from a few deterministic
transition techniques (or pick your own anchor points by hand), fine-tune
the result, and export the rendered transition as a WAV file.

## What it does

- **Upload two tracks.** Audio stays on your device until you explicitly
  analyze or preview/render it — nothing is uploaded just by loading a
  file into the browser.
- **Analyze tempo and beats.** The backend detects each track's BPM, beat
  grid, an estimated musical key, and a shortlist of beats that make
  good transition entry/exit points, based on local energy, structural
  change, and harmonic content.
- **Find transitions.** Given both analyses, the app suggests a base
  anchor pair (which beat of Song A to leave from, which beat of Song B
  to enter on), a tempo interpretation, and starting gain levels — then
  derives three ready-to-audition variants from that same base: a
  Smooth Blend, a Bass Swap (tighter low-end handoff), and a Quick Mix
  (shorter length). Each can be previewed individually before you commit
  to one.
- **Fine-tune by hand.** Anchors can also be picked manually by clicking
  the waveform or stepping beat-by-beat, independent of the suggestion
  flow. The editor exposes transition length, per-track gain trim, blend
  timing, transition style (Smooth / Bass Swap), and bass-swap timing/
  width.
- **Preview and export.** Generate a real rendered preview of the
  transition and listen to it before exporting. Export downloads exactly
  that rendered clip as a WAV file — never a fresh, unheard render.

The transition-suggestion system is a deterministic music-analysis
pipeline (tempo/beat detection, chroma-based key estimation, harmonic
compatibility scoring, candidate ranking) — not a machine-learning or
generative model. The same two analyses always produce the same
suggestion.

## What export produces

Export downloads the transition **clip** currently loaded in the preview
player — the beat-aligned crossfade region around the two chosen anchors,
at the configured transition length. It does not export either song in
full, and it does not stitch together "all of Song A into all of Song B."

## Architecture

Monorepo with two apps:

- **`apps/web`** — Next.js (App Router) + TypeScript + Tailwind CSS +
  WaveSurfer.js frontend. Holds the authoritative `TransitionPlan` state
  and talks to the backend over a small typed HTTP client
  (`src/lib/api.ts`).
- **`apps/api`** — FastAPI + Python backend. Stateless: every request
  carries whatever audio/analysis it needs; uploaded audio is decoded,
  processed, and discarded, never stored. Uses `librosa`/`numpy`/`scipy`
  for analysis and rendering, `soundfile` for WAV I/O.

Design boundaries the codebase keeps deliberately clean:

- Audio processing (backend) is separate from UI code (frontend).
- Automatic transition planning (`transition_planner.py`) is separate
  from audio rendering (`transition_renderer.py`) — planning only ever
  produces a `TransitionPlan`-shaped suggestion; rendering is the single
  place that actually does DSP, reused by every transition style and by
  manual edits alike.
- The manual editor and the automatic suggestion flow operate on the
  exact same `TransitionPlan` representation — adopting a suggested
  variant just replaces the plan's field values, nothing more.

## Prerequisites

- **Backend:** Python 3.14+ and [uv](https://docs.astral.sh/uv/).
- **Frontend:** Node.js 20+ and npm.

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

| Variable              | Purpose                                   | Local default             |
| ---------------------- | ------------------------------------------ | -------------------------- |
| `NEXT_PUBLIC_API_URL` | Base URL the frontend calls for the API.  | `http://localhost:8000`   |

### `apps/api/.env`

| Variable           | Purpose                                              | Local default              |
| ------------------- | ------------------------------------------------------ | ---------------------------- |
| `FRONTEND_ORIGINS` | Comma-separated list of origins allowed via CORS.     | `http://localhost:3000`    |

`FRONTEND_ORIGINS` is optional for local development — it defaults to
`http://localhost:3000` when unset. For a deployed frontend, set it to
that frontend's real origin(s), e.g.
`FRONTEND_ORIGINS=https://your-frontend.example.com`. It is never safe to
set this to `"*"`: the API is served with credentials enabled, and a
wildcard origin combined with credentials is both insecure and rejected
by browsers.

Neither app currently requires any secret values.

## How the workflow works

1. **Add tracks** — load Song A and Song B (drag-and-drop or file picker).
2. **Analyze** — each track is sent to the backend once to detect tempo,
   beats, key, and candidate transition points.
3. **Choose a transition** — either click "Find transitions" to get three
   ready-made options (Smooth Blend / Bass Swap / Quick Mix) and preview
   them individually, or skip straight to picking anchor points by hand
   on each waveform.
4. **Fine-tune** — once anchors are set (from a suggestion or manually),
   the editor lets you adjust transition length, gain, blend timing,
   style, and bass-swap parameters.
5. **Generate a preview** — renders the actual transition audio so you
   can listen before exporting. Any further edit marks that preview
   stale; you always hear the current settings before you can export
   them.
6. **Export** — downloads exactly the rendered preview as a `.wav` file.

## Testing

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

## Current limitations

- Backend processing is entirely stateless and in-memory per request —
  there is no persistent storage, accounts, or history. Nothing is saved
  server-side.
- Every preview or export render re-uploads both full source files to the
  backend; there's no server-side audio cache between requests.
- The renderer only reads a short window of each source track around its
  chosen anchor, so very long or very short transitions outside the
  supported 8/16/32-beat lengths aren't available.
- Key estimation and harmonic-compatibility scoring are heuristic
  (chroma-based Krumhansl-Schmuckler key finding) and report unknown/
  neutral results when a track's tonal content is ambiguous, rather than
  guessing.
- Time-stretching is phase-vocoder based and works best for modest tempo
  differences; large tempo gaps beyond the supported half/double-time
  correction can sound artifacted.
- There is no undo/redo in the manual editor beyond the "Reset mix
  settings" action.
