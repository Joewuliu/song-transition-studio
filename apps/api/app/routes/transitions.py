import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Response, UploadFile
from pydantic import ValidationError

from app.schemas import (
    SuggestedAnchor,
    TransitionRenderRequest,
    TransitionSuggestion,
    TransitionSuggestRequest,
    TransitionSuggestResponse,
)
from app.services.transition_planner import (
    TransitionPlannerError,
    suggest_transition_plan,
)
from app.services.transition_renderer import TransitionRenderError, render_transition
from app.services.upload_validation import read_validated_upload

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
        song_a_tmp = _write_temp_file(song_a_data, Path(song_a.filename or "").suffix)
        song_b_tmp = _write_temp_file(song_b_data, Path(song_b.filename or "").suffix)

        result = render_transition(
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
    candidates already returned by /tracks/analyze."""
    try:
        result = suggest_transition_plan(
            request.song_a_analysis, request.song_b_analysis
        )
    except TransitionPlannerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return TransitionSuggestResponse(
        plan=TransitionSuggestion(
            song_a_anchor=SuggestedAnchor(
                beat_index=result.song_a_anchor.beat_index,
                time_seconds=result.song_a_anchor.time_seconds,
            ),
            song_b_anchor=SuggestedAnchor(
                beat_index=result.song_b_anchor.beat_index,
                time_seconds=result.song_b_anchor.time_seconds,
            ),
            transition_beats=result.transition_beats,
            song_a_gain_db=result.song_a_gain_db,
            song_b_gain_db=result.song_b_gain_db,
            crossfade_bias=result.crossfade_bias,
            song_b_tempo_multiplier=result.song_b_tempo_multiplier,
        ),
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


def _write_temp_file(data: bytes, suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as tmp_file:
        tmp_file.write(data)
    return path


def _format_validation_error(exc: ValidationError) -> str:
    first = exc.errors()[0]
    location = ".".join(str(part) for part in first["loc"]) or "plan"
    return f"Invalid transition plan ({location}): {first['msg']}"
