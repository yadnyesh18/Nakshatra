"""
TTS Coaching Pipeline  —  Nakshatra
=====================================
Real-time LLM coaching via Gemini Flash → Web Speech API (browser TTS).

How it works:
1.  Every N reps (or on Warning/strain), frontend POSTs to /rehab/coach-tts
2.  This service calls Gemini Flash with current session state
3.  Returns a short spoken_cue (≤ 20 words) + severity
4.  Frontend calls:
        const u = new SpeechSynthesisUtterance(spoken_cue);
        u.rate = 0.9; u.pitch = 1.0;
        window.speechSynthesis.speak(u);

Cue is intentionally short and natural-sounding for TTS.
Never mention raw angles to the patient — use directional language.
"""

from __future__ import annotations

import os
from typing import List, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────
# Output schema (validated before sending to frontend)
# ─────────────────────────────────────────────────────────────────

class TTSCoachOutput(BaseModel):
    spoken_cue:          str  = Field(..., description="Natural speech for TTS, max 20 words.")
    visual_text:         str  = Field(..., description="Short UI label, max 6 words.")
    severity:            str  = Field(..., description="'info' | 'warning' | 'correction' | 'praise'")
    should_pause_session:bool = Field(..., description="True only for immediate safety concerns.")


# ─────────────────────────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────────────────────────

_COACH_PROMPT = PromptTemplate(
    input_variables=[
        "exercise", "status", "direction_cue",
        "reps", "sets_done", "strain_events",
        "rehab_day", "accuracy_pct", "stage_label",
    ],
    template="""You are a calm, encouraging physiotherapy coach speaking to a patient via text-to-speech.

Current session data:
- Exercise: {exercise}
- Movement status: {status}   (Correct / Partial / Rest / Warning)
- Direction hint: {direction_cue}   (e.g. "arm below target" or "arm in correct zone")
- Reps this set: {reps}
- Sets completed: {sets_done} of 3
- Strain events: {strain_events}
- Rehab day: {rehab_day}
- Session accuracy: {accuracy_pct}%
- Stage: {stage_label}

Generate a single spoken coaching cue. Follow these rules strictly:
- Correct status   → brief praise OR "hold it" encouragement
- Partial status   → gentle direction to raise/lower/rotate toward target
- Warning/strain   → calm safety cue, slow down, never alarming
- NEVER mention degrees or numbers — use natural directional language
- spoken_cue must sound natural when read aloud by a TTS engine (max 20 words)
- visual_text is a short 2-6 word label shown on screen (not spoken)

Respond ONLY with valid JSON, no markdown fences:
{{
  "spoken_cue": "<natural speech>",
  "visual_text": "<short label>",
  "severity": "info|warning|correction|praise",
  "should_pause_session": false
}}"""
)


# ─────────────────────────────────────────────────────────────────
# Direction cue helper  (no angles to patient — only direction words)
# ─────────────────────────────────────────────────────────────────

def _direction_cue(exercise_key: str, status: str, angle: float, target_min: float, target_max: float) -> str:
    if status == "Correct":
        return "movement is in the correct zone"
    
    exercise_directions = {
        "arm_raise":          ("raise your arm higher",     "lower your arm slightly"),
        "pendulum_swing":     ("swing a little further",    "ease back slightly"),
        "shoulder_abduction": ("lift your arm out sideways","bring it in a little"),
        "shoulder_rotation":  ("rotate outward more",       "rotate inward slightly"),
        "elbow_flexion":      ("bend your elbow more",      "straighten slightly"),
        "elbow_extension":    ("straighten your arm more",  "bend slightly"),
    }
    up_cue, down_cue = exercise_directions.get(exercise_key, ("move further", "ease back"))

    if angle < target_min:
        return f"arm below target — {up_cue}"
    elif angle > target_max:
        return f"arm above target — {down_cue}"
    return "approaching target zone"


# ─────────────────────────────────────────────────────────────────
# Fallback pool (rotated when LLM unavailable)
# ─────────────────────────────────────────────────────────────────

_FALLBACKS = [
    TTSCoachOutput(spoken_cue="Great work, keep moving steadily.",            visual_text="Keep going",      severity="info",       should_pause_session=False),
    TTSCoachOutput(spoken_cue="Gently raise your arm a little higher.",       visual_text="Raise a bit more", severity="info",      should_pause_session=False),
    TTSCoachOutput(spoken_cue="Hold that position — you're doing well.",      visual_text="Hold it",          severity="praise",    should_pause_session=False),
    TTSCoachOutput(spoken_cue="Take a slow breath and ease into the movement.", visual_text="Slow down",      severity="correction",should_pause_session=False),
    TTSCoachOutput(spoken_cue="Excellent — that was a perfect repetition.",   visual_text="Perfect rep!",    severity="praise",    should_pause_session=False),
    TTSCoachOutput(spoken_cue="Listen to your body — slow down if it hurts.", visual_text="⚠ Take it easy", severity="warning",   should_pause_session=False),
]

_fallback_idx = 0


# ─────────────────────────────────────────────────────────────────
# Service class
# ─────────────────────────────────────────────────────────────────

class TTSCoachService:
    """
    Singleton coaching service.
    Call get_coaching_cue() from the /rehab/coach-tts endpoint.
    """

    def __init__(self):
        global _fallback_idx
        _fallback_idx = 0
        api_key    = os.getenv("GOOGLE_API_KEY")
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

        if not api_key:
            print("[TTSCoach] No GOOGLE_API_KEY — using fallback cues only.")
            self._llm   = None
            self._chain = None
            return

        self._llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=0.3,
            max_tokens=180,
        )
        self._chain = _COACH_PROMPT | self._llm | JsonOutputParser()

    async def get_coaching_cue(
        self,
        exercise_key:   str,
        status:         str,
        angle:          float,
        target_min:     float,
        target_max:     float,
        reps:           int,
        sets_done:      int  = 0,
        strain_events:  int  = 0,
        rehab_day:      int  = 1,
        accuracy_pct:   float= 0.0,
        stage_label:    str  = "",
    ) -> TTSCoachOutput:
        """
        Generate a real-time coaching cue.
        Safe to call every 5 reps or on every Warning status.
        """
        global _fallback_idx

        direction = _direction_cue(exercise_key, status, angle, target_min, target_max)

        if not self._chain:
            cue = _FALLBACKS[_fallback_idx % len(_FALLBACKS)]
            _fallback_idx += 1
            return cue

        try:
            result = await self._chain.ainvoke({
                "exercise":     exercise_key.replace("_", " ").title(),
                "status":       status,
                "direction_cue":direction,
                "reps":         reps,
                "sets_done":    sets_done,
                "strain_events":strain_events,
                "rehab_day":    rehab_day,
                "accuracy_pct": round(accuracy_pct, 1),
                "stage_label":  stage_label or f"Day {rehab_day}",
            })
            return TTSCoachOutput(**result)

        except Exception as exc:
            print(f"[TTSCoach] LLM call failed: {exc}")
            cue = _FALLBACKS[_fallback_idx % len(_FALLBACKS)]
            _fallback_idx += 1
            return cue


# ─────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────
tts_coach = TTSCoachService()