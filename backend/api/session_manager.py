"""
Session Manager Service  —  Nakshatra
======================================
Handles the full session lifecycle:
  • Max 3 sessions/day, min 1/day recommended
  • Each session: up to 3 exercises
  • Each exercise: 3 sets × 10 reps
  • 60-second cooldown after each completed exercise (skippable)

In-memory state is used during the hackathon; all dicts are shaped to
mirror the Supabase columns so the swap is a one-liner later.
"""

from __future__ import annotations

import time
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/rehab", tags=["session-manager"])

# ─────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────
MAX_SESSIONS_PER_DAY    = 3
MIN_SESSIONS_PER_DAY    = 1     # recommended minimum
EXERCISES_PER_SESSION   = 3
SETS_PER_EXERCISE       = 3
REPS_PER_SET            = 10
COOLDOWN_DURATION_SEC   = 60

# ─────────────────────────────────────────────────────────────────
# In-memory state  (replace with Supabase queries after hackathon)
# ─────────────────────────────────────────────────────────────────
_daily_sessions:  Dict[str, List[Dict]] = {}   # "uid:YYYY-MM-DD" → [session dicts]
_active_sessions: Dict[str, Dict]       = {}   # session_id → full session state
_cooldowns:       Dict[str, float]      = {}   # session_id → unix timestamp of cooldown end


# ─────────────────────────────────────────────────────────────────
# Pydantic request / response models
# ─────────────────────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    user_id: str

class StartExerciseRequest(BaseModel):
    user_id: str
    session_id: str
    exercise_key: str
    stage: int = 1

class CompleteSetRequest(BaseModel):
    user_id: str
    session_id: str
    exercise_key: str
    set_number: int            # 1-indexed
    reps_completed: int
    avg_angle: float
    accuracy_pct: float
    strain_events: int = 0

class CompleteExerciseRequest(BaseModel):
    user_id: str
    session_id: str
    exercise_key: str

class SkipCooldownRequest(BaseModel):
    user_id: str
    session_id: str


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _day_key(user_id: str) -> str:
    return f"{user_id}:{date.today().isoformat()}"

def _sessions_today(user_id: str) -> List[Dict]:
    return _daily_sessions.get(_day_key(user_id), [])

def _completed_today(user_id: str) -> int:
    return sum(1 for s in _sessions_today(user_id) if s.get("completed"))

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


# ─────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────

@router.get("/daily-status/{user_id}", summary="Get today's session count and status")
def daily_status(user_id: str):
    sessions = _sessions_today(user_id)
    completed = _completed_today(user_id)
    return {
        "user_id":               user_id,
        "date":                  date.today().isoformat(),
        "sessions_completed":    completed,
        "sessions_remaining":    max(0, MAX_SESSIONS_PER_DAY - completed),
        "min_recommended":       MIN_SESSIONS_PER_DAY,
        "max_allowed":           MAX_SESSIONS_PER_DAY,
        "today_done":            completed >= MIN_SESSIONS_PER_DAY,
        "sessions":              sessions,
    }


@router.post("/session/start", summary="Start a new rehab session for today")
def start_session(req: StartSessionRequest):
    # Get all sessions started today (completed or not)
    todays_sessions = _sessions_today(req.user_id)
    
    # 1. Enforce the hard daily limit
    if len(todays_sessions) >= MAX_SESSIONS_PER_DAY:
        raise HTTPException(
            status_code=403, # Changed to 403 Forbidden to match the expected stress test
            detail=f"Daily limit of {MAX_SESSIONS_PER_DAY} sessions reached. Rest is critical for recovery!"
        )

    # 2. Prevent starting a new session if they have an active one
    for s in todays_sessions:
        if not s.get("completed"):
            raise HTTPException(
                status_code=400,
                detail="You already have an active session. Please complete or cancel it first."
            )

    session_number = len(todays_sessions) + 1
    session_id = f"{req.user_id}:s{session_number}:{int(time.time())}"

    state: Dict[str, Any] = {
        "session_id":      session_id,
        "user_id":         req.user_id,
        "session_number":  session_number,
        "started_at":      _now_iso(),
        "completed":       False,
        "completed_at":    None,
        "exercises":       [],
        "cooldown_active": False,
        "cooldown_ends_at": None,
    }

    _active_sessions[session_id] = state
    _daily_sessions.setdefault(_day_key(req.user_id), []).append(state)

    return {
        "session_id":        session_id,
        "session_number":    session_number,
        "exercises_allowed": EXERCISES_PER_SESSION,
        "sets_per_exercise": SETS_PER_EXERCISE,
        "reps_per_set":      REPS_PER_SET,
        "message":           f"Session {session_number} started. Let's go! 🚀",
    }


@router.post("/exercise/start", summary="Mark an exercise as started within a session")
def start_exercise(req: StartExerciseRequest):
    session = _active_sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found.")
    if session["completed"]:
        raise HTTPException(400, "Session already completed.")

    # Block if cooldown is still active
    cd_end = _cooldowns.get(req.session_id, 0)
    if time.time() < cd_end:
        remaining = int(cd_end - time.time())
        raise HTTPException(
            409,
            f"Cooldown active — {remaining}s remaining. "
            f"POST /rehab/session/skip-cooldown to skip."
        )

    # Count exercises already started (including incomplete ones to prevent double-start)
    started = [e for e in session["exercises"] if e["exercise_key"] == req.exercise_key and not e.get("completed")]
    if started:
        raise HTTPException(409, f"Exercise '{req.exercise_key}' is already active in this session.")

    completed_exercises = sum(1 for e in session["exercises"] if e.get("completed"))
    if completed_exercises >= EXERCISES_PER_SESSION:
        raise HTTPException(400, "All exercises for this session are already done.")

    ex_record: Dict[str, Any] = {
        "exercise_key": req.exercise_key,
        "stage":        req.stage,
        "started_at":   _now_iso(),
        "sets":         [],
        "completed":    False,
        "completed_at": None,
    }
    session["exercises"].append(ex_record)

    return {
        "message":           f"Exercise '{req.exercise_key}' started.",
        "exercise_number":   completed_exercises + 1,
        "of_total":          EXERCISES_PER_SESSION,
        "sets_required":     SETS_PER_EXERCISE,
        "reps_per_set":      REPS_PER_SET,
    }


@router.post("/set/complete", summary="Record a completed set for the current exercise")
def complete_set(req: CompleteSetRequest):
    session = _active_sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found.")

    # Find the active (not yet completed) exercise record
    active_ex = next(
        (e for e in reversed(session["exercises"])
         if e["exercise_key"] == req.exercise_key and not e["completed"]),
        None,
    )
    if not active_ex:
        raise HTTPException(404, f"No active exercise '{req.exercise_key}' found in session.")

    if len(active_ex["sets"]) >= SETS_PER_EXERCISE:
        raise HTTPException(400, f"Already recorded {SETS_PER_EXERCISE} sets for this exercise.")

    set_record = {
        "set_number":       req.set_number,
        "reps_completed":   req.reps_completed,
        "avg_angle":        round(req.avg_angle, 2),
        "accuracy_pct":     round(req.accuracy_pct, 2),
        "strain_events":    req.strain_events,
        "timestamp":        _now_iso(),
    }
    active_ex["sets"].append(set_record)

    sets_done      = len(active_ex["sets"])
    sets_remaining = SETS_PER_EXERCISE - sets_done

    return {
        "set_recorded":   set_record,
        "sets_done":      sets_done,
        "sets_remaining": sets_remaining,
        "all_sets_done":  sets_remaining == 0,
        "next_action":    "complete_exercise" if sets_remaining == 0 else f"do set {sets_done + 1}",
    }


@router.post("/exercise/complete", summary="Mark exercise as done — starts 60s cooldown")
def complete_exercise(req: CompleteExerciseRequest):
    session = _active_sessions.get(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found.")

    active_ex = next(
        (e for e in reversed(session["exercises"])
         if e["exercise_key"] == req.exercise_key and not e["completed"]),
        None,
    )
    if not active_ex:
        raise HTTPException(404, "No active exercise found to complete.")

    active_ex["completed"]    = True
    active_ex["completed_at"] = _now_iso()

    # Compute summary for this exercise
    sets = active_ex["sets"]
    if sets:
        active_ex["avg_accuracy"] = round(sum(s["accuracy_pct"] for s in sets) / len(sets), 1)
        active_ex["total_reps"]   = sum(s["reps_completed"] for s in sets)

    exercises_done    = sum(1 for e in session["exercises"] if e["completed"])
    session_complete  = exercises_done >= EXERCISES_PER_SESSION

    response: Dict[str, Any] = {
        "exercise_completed": req.exercise_key,
        "exercises_done":     exercises_done,
        "of_total":           EXERCISES_PER_SESSION,
        "session_complete":   session_complete,
    }

    if session_complete:
        session["completed"]    = True
        session["completed_at"] = _now_iso()
        response["message"] = "🎉 Session complete! Great work today."
        response["cooldown_started"] = False
    else:
        # Start 60-second cooldown
        cd_end = time.time() + COOLDOWN_DURATION_SEC
        _cooldowns[req.session_id]    = cd_end
        session["cooldown_active"]    = True
        session["cooldown_ends_at"]   = datetime.utcfromtimestamp(cd_end).isoformat() + "Z"
        response["cooldown_started"]  = True
        response["cooldown_seconds"]  = COOLDOWN_DURATION_SEC
        response["message"]           = (
            f"✅ Exercise done! Rest for {COOLDOWN_DURATION_SEC}s "
            f"before starting exercise {exercises_done + 1}/{EXERCISES_PER_SESSION}."
        )

    return response


@router.post("/session/skip-cooldown", summary="Skip the current cooldown timer")
def skip_cooldown(req: SkipCooldownRequest):
    _cooldowns.pop(req.session_id, None)
    session = _active_sessions.get(req.session_id)
    if session:
        session["cooldown_active"]  = False
        session["cooldown_ends_at"] = None
    return {"message": "Cooldown skipped.", "session_id": req.session_id}


@router.get("/cooldown-status/{session_id}", summary="Check remaining cooldown time")
def cooldown_status(session_id: str):
    cd_end = _cooldowns.get(session_id, 0)
    remaining = max(0, cd_end - time.time())
    return {
        "active":           remaining > 0,
        "remaining_seconds": int(remaining),
        "total_seconds":    COOLDOWN_DURATION_SEC,
        "progress":         round(1 - remaining / COOLDOWN_DURATION_SEC, 3) if remaining > 0 else 1.0,
    }


@router.get("/session/{session_id}", summary="Get full session state")
def get_session(session_id: str):
    session = _active_sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found.")
    return session