import asyncio
import os
import tempfile

from fastapi import APIRouter, Form, HTTPException, Response, UploadFile
from pydantic import ValidationError

from app.schemas import (
    SuggestedAnchor,
    TransitionRenderRequest,
    TransitionSuggestion,
    TransitionSuggestRequest,
    TransitionSuggestResponse,
    TransitionVariant,
)
from app.services.transition_planner import (
    AnchorChoice,
    TransitionPlannerError,
    build_transition_variants,
    suggest_transition_plan,
)
from app.services.transition_renderer import TransitionRenderError, render_transition
from app.services.upload_validation import read_validated_upload, safe_temp_suffix

router = APIRouter(prefix="/transitions", tags=["transitions"])


@router.post("/render")
async def render_transition_preview(
    song_a: UploadFile,
    song_b: UploadFile,
    plan: str = Form(...),
) -> Response:
    try:
        parsed_plan = TransitionRenderRequest.model_validate_json(plan)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail=_format_validation_error(exc)
        ) from exc

    song_a_data = await read_validated_upload(song_a, label="Song A")
    song_b_data = await read_validated_upload(song_b, label="Song B")

    song_a_tmp: str | None = None
    song_b_tmp: str | None = None
    try:
        song_a_tmp = _write_temp_file(
            song_a_data, safe_temp_suffix(song_a.filename or "")
        )
        song_b_tmp = _write_temp_file(
            song_b_data, safe_temp_suffix(song_b.filename or "")
        )

        # render_transition is a plain synchronous, CPU-heavy call
        # (resampling, phase-vocoder time-stretching, filtering) — see the
        # same note in routes/tracks.py. Offloading it keeps the event
        # loop free for other requests while this one renders.
        result = await asyncio.to_thread(
            render_transition,
            song_a_path=song_a_tmp,
            song_b_path=song_b_tmp,
            song_a_anchor_seconds=parsed_plan.song_a_anchor.time_seconds,
            song_b_anchor_seconds=parsed_plan.song_b_anchor.time_seconds,
            song_a_bpm=parsed_plan.song_a_bpm,
            song_b_bpm=parsed_plan.song_b_bpm,
            transition_beats=parsed_plan.transition_beats,
            song_a_gain_db=parsed_plan.song_a_gain_db,
            song_b_gain_db=parsed_plan.song_b_gain_db,
            crossfade_bias=parsed_plan.crossfade_bias,
            song_b_tempo_multiplier=parsed_plan.song_b_tempo_multiplier,
            transition_style=parsed_plan.transition_style,
            bass_swap_position=parsed_plan.bass_swap_position,
            bass_swap_width_beats=parsed_plan.bass_swap_width_beats,
        )
    except TransitionRenderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        for tmp_path in (song_a_tmp, song_b_tmp):
            if tmp_path is not None:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    return Response(
        content=result.wav_bytes,
        media_type="audio/wav",
        headers={
            "X-Target-Bpm": f"{result.target_bpm:.3f}",
            "X-Preview-Duration-Seconds": f"{result.duration_seconds:.3f}",
        },
    )


@router.post("/suggest", response_model=TransitionSuggestResponse)
async def suggest_transition(
    request: TransitionSuggestRequest,
) -> TransitionSuggestResponse:
    """Suggests a starting TransitionPlan from two already-computed track
    analyses — no audio upload needed, since planning only needs the beats/
    candidates already returned by /tracks/analyze.

    Also returns three deterministic presentation variants (Smooth Blend /
    Bass Swap / Quick Mix) derived from that SAME base plan — same anchors,
    tempo interpretation, and starting gains throughout; see
    services/transition_planner.build_transition_variants."""
    try:
        result = suggest_transition_plan(
            request.song_a_analysis, request.song_b_analysis
        )
    except TransitionPlannerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    variants = build_transition_variants(result)

    return TransitionSuggestResponse(
        plan=_suggestion_schema(
            song_a_anchor=result.song_a_anchor,
            song_b_anchor=result.song_b_anchor,
            transition_beats=result.transition_beats,
            song_a_gain_db=result.song_a_gain_db,
            song_b_gain_db=result.song_b_gain_db,
            crossfade_bias=result.crossfade_bias,
            song_b_tempo_multiplier=result.song_b_tempo_multiplier,
        ),
        variants=[
            TransitionVariant(
                id=variant.id,
                name=variant.name,
                description=variant.description,
                plan=_suggestion_schema(
                    song_a_anchor=variant.plan.song_a_anchor,
                    song_b_anchor=variant.plan.song_b_anchor,
                    transition_beats=variant.plan.transition_beats,
                    song_a_gain_db=variant.plan.song_a_gain_db,
                    song_b_gain_db=variant.plan.song_b_gain_db,
                    crossfade_bias=variant.plan.crossfade_bias,
                    song_b_tempo_multiplier=variant.plan.song_b_tempo_multiplier,
                    transition_style=variant.plan.transition_style,
                    bass_swap_position=variant.plan.bass_swap_position,
                    bass_swap_width_beats=variant.plan.bass_swap_width_beats,
                ),
            )
            for variant in variants
        ],
        effective_song_b_bpm=round(result.effective_song_b_bpm, 3),
        tempo_compatibility=result.tempo_compatibility,
        used_tempo_normalization=result.song_b_tempo_multiplier != 1.0,
        song_a_anchor_source="candidate"
        if result.song_a_anchor.from_candidate
        else "fallback",
        song_b_anchor_source="candidate"
        if result.song_b_anchor.from_candidate
        else "fallback",
        harmonic_compatibility=round(result.harmonic_compatibility, 4),
        song_a_local_key=result.song_a_anchor.local_key,
        song_a_local_mode=result.song_a_anchor.local_mode,
        song_b_local_key=result.song_b_anchor.local_key,
        song_b_local_mode=result.song_b_anchor.local_mode,
    )


def _suggestion_schema(
    *,
    song_a_anchor: AnchorChoice,
    song_b_anchor: AnchorChoice,
    transition_beats: int,
    song_a_gain_db: float,
    song_b_gain_db: float,
    crossfade_bias: float,
    song_b_tempo_multiplier: float,
    transition_style: str = "smooth",
    bass_swap_position: float = 0.5,
    bass_swap_width_beats: int = 4,
) -> TransitionSuggestion:
    """Builds one TransitionSuggestion schema instance — used for both the
    top-level `plan` and every variant's `plan`, so the mapping from
    planner output to API shape is written exactly once."""
    return TransitionSuggestion(
        song_a_anchor=SuggestedAnchor(
            beat_index=song_a_anchor.beat_index,
            time_seconds=song_a_anchor.time_seconds,
        ),
        song_b_anchor=SuggestedAnchor(
            beat_index=song_b_anchor.beat_index,
            time_seconds=song_b_anchor.time_seconds,
        ),
        transition_beats=transition_beats,
        song_a_gain_db=song_a_gain_db,
        song_b_gain_db=song_b_gain_db,
        crossfade_bias=crossfade_bias,
        song_b_tempo_multiplier=song_b_tempo_multiplier,
        transition_style=transition_style,
        bass_swap_position=bass_swap_position,
        bass_swap_width_beats=bass_swap_width_beats,
    )


def _write_temp_file(data: bytes, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as tmp_file:
        tmp_file.write(data)
    return path


def _format_validation_error(exc: ValidationError) -> str:
    first = exc.errors()[0]
    location = ".".join(str(part) for part in first["loc"]) or "plan"
    return f"Invalid transition plan ({location}): {first['msg']}"
