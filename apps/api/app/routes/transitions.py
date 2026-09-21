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
)
from app.schemas import (
    TransitionChoice as TransitionChoiceSchema,
)
from app.services.transition_planner import (
    TransitionChoice,
    TransitionPlannerError,
    suggest_transition_choices,
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
    """Suggests up to three distinct, ready-to-adopt transition choices from
    two already-computed track analyses — no audio upload needed, since
    planning only needs the beats/candidates already returned by
    /tracks/analyze.

    M12: each choice represents a genuinely different Song A exit / Song B
    entry anchor PAIR (not the same anchors presented three different
    ways) — see services/transition_planner.suggest_transition_choices."""
    try:
        result = suggest_transition_choices(
            request.song_a_analysis, request.song_b_analysis
        )
    except TransitionPlannerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return TransitionSuggestResponse(
        choices=[_choice_schema(choice) for choice in result.choices],
        effective_song_b_bpm=round(result.effective_song_b_bpm, 3),
        tempo_compatibility=result.tempo_compatibility,
        used_tempo_normalization=result.used_tempo_normalization,
        song_a_anchor_source=result.song_a_anchor_source,
        song_b_anchor_source=result.song_b_anchor_source,
    )


def _choice_schema(choice: TransitionChoice) -> TransitionChoiceSchema:
    return TransitionChoiceSchema(
        id=choice.id,
        label=choice.label,
        description=choice.description,
        plan=TransitionSuggestion(
            song_a_anchor=SuggestedAnchor(
                beat_index=choice.song_a_anchor.beat_index,
                time_seconds=choice.song_a_anchor.time_seconds,
            ),
            song_b_anchor=SuggestedAnchor(
                beat_index=choice.song_b_anchor.beat_index,
                time_seconds=choice.song_b_anchor.time_seconds,
            ),
            transition_beats=choice.transition_beats,
            song_a_gain_db=choice.song_a_gain_db,
            song_b_gain_db=choice.song_b_gain_db,
            crossfade_bias=choice.crossfade_bias,
            song_b_tempo_multiplier=choice.song_b_tempo_multiplier,
            transition_style=choice.transition_style,
            bass_swap_position=choice.bass_swap_position,
            bass_swap_width_beats=choice.bass_swap_width_beats,
        ),
        compatibility=choice.compatibility,
        harmonic_compatibility=choice.harmonic_compatibility,
        song_a_local_key=choice.song_a_anchor.local_key,
        song_a_local_mode=choice.song_a_anchor.local_mode,
        song_b_local_key=choice.song_b_anchor.local_key,
        song_b_local_mode=choice.song_b_anchor.local_mode,
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
