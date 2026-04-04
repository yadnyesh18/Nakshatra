"""
Cognitive Games Service  —  Nakshatra
=======================================
Handles all cognitive mini-game data:
  • Record game session results
  • AI-powered difficulty recommendations (LangChain / Gemini Flash)
  • Per-game progress + overall cognitive score
  • Data shaped to match the new Supabase columns (see schema.sql)

Supported games (extensible):
  • memory_constellation
  • (add more game_name strings as you build them)

Frontend result payload expected:
  {
    "user_id":      "uuid",
    "game_name":    "memory_constellation",
    "level_reached": 3,
    "accuracy_pct":  67.0,
    "cog_score":     49.0,
    "duration_sec":  120.5,
    "metadata":      {}     // optional extra fields per game
  }

UI display response matches the design spec:
  headline:    "Keep Practising"
  subtitle:    "Level 3 reached — 67% accuracy. Every session builds..."
  stats:       { cog_score: 49, accuracy: 67, best_level: 3 }
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from logic.cognitive_llm import cognitive_llm

router = APIRouter(prefix="/cognitive", tags=["cognitive-games"])


# ─────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────

class GameResultRequest(BaseModel):
    user_id:       str
    game_name:     str
    level_reached: int
    accuracy_pct:  float
    cog_score:     float
    duration_sec:  float
    metadata:      Optional[Dict[str, Any]] = {}

class DifficultyRequest(BaseModel):
    user_id:   str
    game_name: str


# ─────────────────────────────────────────────────────────────────
# In-memory store
# Each entry mirrors the columns you'll add to the Supabase users/games table.
# Replace _game_history lookups with Supabase queries after the hackathon.
# ─────────────────────────────────────────────────────────────────

_game_history: Dict[str, List[Dict]] = {}   # "uid:game_name" → [session records]


def _hkey(user_id: str, game_name: str) -> str:
    return f"{user_id}:{game_name}"

def _get_history(user_id: str, game_name: str) -> List[Dict]:
    return _game_history.get(_hkey(user_id, game_name), [])

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


# ─────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────

@router.post("/game/result", summary="Record a completed game session result")
async def record_game_result(req: GameResultRequest):
    """
    Called by the frontend immediately after a game session ends.
    Returns the UI display payload (headline, stats, feedback).
    """
    record: Dict[str, Any] = {
        "game_name":     req.game_name,
        "level_reached": req.level_reached,
        "accuracy_pct":  round(req.accuracy_pct, 2),
        "cog_score":     round(req.cog_score, 2),
        "duration_sec":  round(req.duration_sec, 1),
        "metadata":      req.metadata or {},
        "timestamp":     _now_iso(),
    }

    k = _hkey(req.user_id, req.game_name)
    _game_history.setdefault(k, []).append(record)
    history = _game_history[k]

    # AI feedback (async, falls back gracefully)
    feedback_msg = await cognitive_llm.generate_feedback(
        game_name  = req.game_name,
        level      = req.level_reached,
        accuracy   = req.accuracy_pct,
        cog_score  = req.cog_score,
        history    = history,
    )

    # Overall cognitive score across all games for this user (rolling avg)
    all_recent_scores = [
        r["cog_score"]
        for key, records in _game_history.items()
        if key.startswith(f"{req.user_id}:")
        for r in records[-5:]
    ]
    overall_cog = (
        round(sum(all_recent_scores) / len(all_recent_scores), 1)
        if all_recent_scores else req.cog_score
    )

    best_level = max(r["level_reached"] for r in history)

    return {
        "recorded":          True,
        "game_name":         req.game_name,
        "session":           record,
        "best_level":        best_level,
        "overall_cog_score": overall_cog,

        # ── UI display payload ── matches the design spec exactly ──
        "ui_display": _build_ui_display(
            game_name   = req.game_name,
            level       = req.level_reached,
            accuracy    = req.accuracy_pct,
            cog_score   = req.cog_score,
            best_level  = best_level,
            overall_cog = overall_cog,
            feedback    = feedback_msg,
        ),
    }


@router.get("/progress/{user_id}/{game_name}", summary="Get per-game progress for a user")
def get_game_progress(user_id: str, game_name: str):
    history = _get_history(user_id, game_name)
    if not history:
        return {
            "user_id":   user_id,
            "game_name": game_name,
            "sessions_played": 0,
            "message": "No sessions recorded yet.",
        }

    scores   = [r["cog_score"]     for r in history]
    accuries = [r["accuracy_pct"]  for r in history]

    return {
        "user_id":        user_id,
        "game_name":      game_name,
        "sessions_played":len(history),
        "best_level":     max(r["level_reached"] for r in history),
        "best_accuracy":  round(max(accuries), 1),
        "avg_cog_score":  round(sum(scores) / len(scores), 1),
        "recent_trend":   _compute_trend(history),
        "history":        history[-10:],   # last 10 for charts
    }


@router.post("/difficulty/recommend", summary="Get AI-recommended next difficulty level")
async def recommend_difficulty(req: DifficultyRequest):
    """
    Call this before starting a new game session to get the recommended level.
    AI keeps the patient in a 'flow state' — not too easy, not too hard.
    """
    history        = _get_history(req.user_id, req.game_name)
    recommendation = await cognitive_llm.predict_difficulty(req.game_name, history)
    return {
        "user_id":   req.user_id,
        "game_name": req.game_name,
        **recommendation,
    }


@router.get("/overall/{user_id}", summary="Aggregate cognitive progress across all games")
def get_overall_progress(user_id: str):
    """
    Returns an overall cognitive score and per-game breakdown.
    Displayed on the main dashboard.
    """
    per_game: Dict[str, Any] = {}

    for key, records in _game_history.items():
        if not key.startswith(f"{user_id}:"):
            continue
        game = key.split(":", 1)[1]
        scores = [r["cog_score"] for r in records]
        per_game[game] = {
            "sessions_played": len(records),
            "best_level":      max(r["level_reached"] for r in records),
            "avg_cog_score":   round(sum(scores) / len(scores), 1),
            "best_accuracy":   round(max(r["accuracy_pct"] for r in records), 1),
            "last_played":     records[-1]["timestamp"],
            "trend":           _compute_trend(records),
        }

    all_avgs  = [v["avg_cog_score"] for v in per_game.values()]
    overall   = round(sum(all_avgs) / len(all_avgs), 1) if all_avgs else 0

    return {
        "user_id":           user_id,
        "overall_cog_score": overall,
        "games_played":      list(per_game.keys()),
        "per_game":          per_game,
    }


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _build_ui_display(
    game_name:   str,
    level:       int,
    accuracy:    float,
    cog_score:   float,
    best_level:  int,
    overall_cog: float,
    feedback:    str,
) -> Dict[str, Any]:
    """
    Builds the exact UI payload matching the design spec.

    Design spec output:
        Keep Practising
        Level 3 reached — 67% accuracy. Every session builds stronger neural connections.
        49% Cog Score   67% Accuracy   L3 Best Level
    """
    if accuracy >= 85:
        headline = "Excellent Work! 🌟"
    elif accuracy >= 65:
        headline = "Keep Practising"
    elif accuracy >= 45:
        headline = "You're Making Progress"
    else:
        headline = "Keep Going — Every Rep Counts"

    return {
        "headline": headline,
        "subtitle": f"Level {level} reached — {accuracy:.0f}% accuracy. {feedback}",
        "stats": {
            "cog_score":  int(round(overall_cog)),
            "accuracy":   int(round(accuracy)),
            "best_level": best_level,
        },
        "stat_labels": {
            "cog_score":  "Cog Score",
            "accuracy":   "Accuracy",
            "best_level": "Best Level",
        },
    }


def _compute_trend(history: List[Dict]) -> str:
    if len(history) < 2:
        return "not enough data"
    recent  = [r["cog_score"] for r in history[-3:]]
    earlier = [r["cog_score"] for r in history[-6:-3]] or recent
    delta   = sum(recent) / len(recent) - sum(earlier) / len(earlier)
    if delta > 5:
        return "improving"
    elif delta < -5:
        return "declining"
    return "stable"