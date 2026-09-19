# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Hobbyist DJs and mixers. They have two local audio tracks and want a smooth, beat-aligned transition between them, with hands-on control over how it is performed. They load the tracks, audition options, fine-tune the result, and export it.

## Product Purpose

Song Transition Studio builds DJ-style transitions between two songs and lets the user edit them. It analyzes tempo, beat grid and estimated key for each track, suggests where and how to transition, and renders a real preview the user can listen to and then export as a WAV file.

Success follows the product's own workflow: the user ends with a rendered preview that matches their current settings and exports exactly that audio.

## Positioning

Four mechanisms distinguish it, each true of the current implementation:

- **Deterministic planning.** Tempo, beat and key analysis plus rule-based suggestions. There is no machine-learning or generative model, and the same two tracks always produce the same suggestion.
- **One shared plan.** Automatic suggestions and manual edits operate on the same transition plan, so "suggested", "edited" and "exported" are never different things.
- **Hear it, then export it.** Export is exactly the fresh preview the user listened to. An out-of-date preview stays playable for comparison but cannot be exported.
- **Local-first input.** It works from the user's own audio files. No streaming service is required.

## Operating Context

- Two routes: setup at `/` (load and analyze tracks, find transition options, audition them) and a dedicated editor at `/editor` (decks, mixer controls, transition visualization, preview and export).
- Workflow: add two tracks, analyze, then either "Find transitions" (Smooth Blend, Bass Swap, Quick Mix, previewable individually) or pick anchor beats by hand on each waveform; open the editor, adjust, generate a preview, export the WAV. Manual anchor selection is always available and never requires suggestions.
- Loaded files are held in browser memory only. Audio is sent to the backend for analysis and for each preview render, and is not stored there.
- Monorepo: Next.js, TypeScript, Tailwind CSS and WaveSurfer.js frontend; stateless FastAPI and Python backend using librosa, NumPy, SciPy and soundfile.

## Capabilities and Constraints

- Editable in the editor: transition length (8, 16 or 32 beats), style (Smooth or Bass Swap), per-track level, blend timing, and for Bass Swap the swap timing and width. Each deck offers waveform seeking, previous/next beat, and play/pause.
- Export is the transition clip only, not either song in full.
- The suggestion system reports unknown or neutral results (for example an ambiguous key) rather than guessing.
- The analysis detects beats, tempo and an estimated key. It does not detect downbeats, bars, phrases or song sections, and copy must not imply that it does.
- No accounts, database or persistence. A reload clears loaded tracks, and `/editor` shows a recovery state when the required tracks, analyses or anchors are missing.
- No undo or redo beyond "Reset mix settings".
- Internal names such as crossfade bias and tempo multiplier are not shown to users; the user-facing terms are "Blend timing", "Bass swap", "Find transitions" and "Use in editor".
- Transition options are never given evaluative labels such as "Best" or "Recommended".
- Undecided: production hosting and any public demo URL.

## Brand Commitments

- Name: Song Transition Studio. No logo or brand assets exist yet.
- Voice: plain and factual. No inflated claims, and the suggestion system is never described as AI or machine learning.
- The repository carries no tool or vendor attribution.

## Evidence on Hand

- A root README describing features, architecture, setup, deployment and limitations.
- A backend automated test suite built on synthetic audio only.
- Absences that future work must not fabricate: there are no screenshots, no demo link, no user testimonials, and no real music files in the repository.

## Product Principles

1. What you hear is what you export. Nothing stale is ever presented as current.
2. Deterministic and explainable: the same inputs give the same suggestion, and unknown stays unknown.
3. One plan, two ways in: suggested and manual paths are equals, and neither is a dead end.
4. Local-first: nothing leaves the user's device until they ask for analysis, preview or export.
5. Controls are real. Nothing on screen imitates hardware or software features the product does not have.

## Accessibility & Inclusion

Target WCAG 2.2 AA:

- Keyboard-operable controls using native elements where possible.
- Sufficient contrast for text and for control boundaries and states.
- Labelled inputs and visible focus.
- State conveyed by more than color alone.
- Live-region announcements for asynchronous status such as analysis, preview generation and errors.
- Non-pointer alternatives to waveform interaction (previous/next beat).
