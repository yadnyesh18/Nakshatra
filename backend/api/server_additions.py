"""
server_additions.py  —  Nakshatra
===================================
New routes to ADD to the existing backend/api/server.py.

Instructions:
  1. Copy the imports block into server.py imports section.
  2. Copy the route functions into server.py (before the if __name__ block).
  3. Make sure tts_coach and rehab_math are importable (they're in backend/logic/).

These routes extend the existing /api/v1 router.
"""

# ─── ADD THESE TO server.py IMPORTS ──────────────────────────────
# from backend.logic.tts_pipeline import tts_coach, TTSCoachOutput
# from backend.logic.rehab_math import compute_rom_thresholds, compute_strain_risk
# ─────────────────────────────────────────────────────────────────

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

# These would normally come from the shared router in server.py
router = APIRouter()


# ─────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────

class CoachTTSRequest(BaseModel):
    exercise_key:   str
    status:         str          # "Correct" | "Partial" | "Rest" | "Warning"
    angle:          float
    target_min:     float
    target_max:     float
    reps:           int
    sets_done:      int  = 0
    strain_events:  int  = 0
    rehab_day:      int  = 1
    accuracy_pct:   float = 0.0
    stage_label:    Optional[str] = ""

class ROMThresholdRequest(BaseModel):
    exercise_key:      str
    rehab_day:         int
    pain_tolerance:    float = 1.0    # 0.5–1.0
    body_angle_offset: float = 0.0   # from BodyAnalyzer

class StrainRiskRequest(BaseModel):
    angle_drop_deg:            float
    consecutive_strain_events: int
    session_duration_sec:      float


# ─────────────────────────────────────────────────────────────────
# Routes (copy these functions into server.py)
# ─────────────────────────────────────────────────────────────────

@router.post(
    "/session/coach-tts",
    summary="Get a real-time TTS coaching cue from Gemini Flash",
    tags=["coaching"],
)
async def get_tts_coaching_cue(req: CoachTTSRequest):
    """
    Returns a spoken coaching cue for Web Speech API.

    Frontend usage:
        const res = await fetch('/api/v1/session/coach-tts', { method:'POST', body: JSON.stringify(data) });
        const { spoken_cue, severity, should_pause_session } = await res.json();
        if (spoken_cue) {
            const u = new SpeechSynthesisUtterance(spoken_cue);
            u.rate = 0.92; u.pitch = 1.05;
            window.speechSynthesis.cancel();   // stop any previous cue
            window.speechSynthesis.speak(u);
        }

    Call this:
      • Every 5 reps (background polling from the camera worker)
      • Immediately on status == "Warning"
      • Immediately on strain_events increment
    """
    from backend.logic.tts_pipeline import tts_coach
    cue = await tts_coach.get_coaching_cue(
        exercise_key  = req.exercise_key,
        status        = req.status,
        angle         = req.angle,
        target_min    = req.target_min,
        target_max    = req.target_max,
        reps          = req.reps,
        sets_done     = req.sets_done,
        strain_events = req.strain_events,
        rehab_day     = req.rehab_day,
        accuracy_pct  = req.accuracy_pct,
        stage_label   = req.stage_label or "",
    )
    return cue.model_dump()


@router.post(
    "/rom-thresholds",
    summary="Compute day-specific ROM thresholds using the exponential progression model",
    tags=["rehab-math"],
)
def get_rom_thresholds(req: ROMThresholdRequest):
    """
    Use this to dynamically override ExerciseClassifier thresholds
    based on how far along the patient is in their rehab protocol.

    Wire this into the session/start flow:
      1. Fetch thresholds for (exercise_key, user.rehab_day)
      2. Override EXERCISES[exercise_key]["stages"][current_stage] thresholds
    """
    from backend.logic.rehab_math import compute_rom_thresholds
    thresh = compute_rom_thresholds(
        exercise_key      = req.exercise_key,
        rehab_day         = req.rehab_day,
        pain_tolerance    = req.pain_tolerance,
        body_angle_offset = req.body_angle_offset,
    )
    return {
        "exercise_key":    req.exercise_key,
        "rehab_day":       req.rehab_day,
        "correct_min":     thresh.correct_min,
        "correct_max":     thresh.correct_max,
        "partial_min":     thresh.partial_min,
        "target_angle":    thresh.target_angle,
        "stage_label":     thresh.stage_label,
        "progression_pct": thresh.progression_pct,
    }


@router.post(
    "/strain-risk",
    summary="Compute strain risk score for safety monitoring",
    tags=["rehab-math"],
)
def get_strain_risk(req: StrainRiskRequest):
    """
    Call this whenever a strain event is detected.
    If should_pause is True, surface a prominent warning to the user
    and log for clinician review.
    """
    from backend.logic.rehab_math import compute_strain_risk
    risk = compute_strain_risk(
        angle_drop_deg            = req.angle_drop_deg,
        consecutive_strain_events = req.consecutive_strain_events,
        session_duration_sec      = req.session_duration_sec,
    )
    return risk.__dict__