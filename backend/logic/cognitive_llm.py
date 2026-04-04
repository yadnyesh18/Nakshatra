"""
Cognitive LLM Pipeline  —  Nakshatra
======================================
LangChain chains for:
  1. Difficulty prediction   — keeps user in the "flow zone" (not too hard/easy)
  2. Session feedback        — warm, clinically grounded motivational message

Uses Gemini Flash for both (low latency, suitable for post-session display).
Gracefully degrades to rule-based fallback when API is unavailable.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────
# Output schemas
# ─────────────────────────────────────────────────────────────────

class DifficultyRecommendation(BaseModel):
    recommended_level: int   = Field(..., ge=1, le=10)
    reasoning:         str   = Field(...)
    sweet_spot_range:  list  = Field(...)    # [min_level, max_level]
    should_escalate:   bool  = Field(...)
    should_deescalate: bool  = Field(...)

class CognitiveFeedback(BaseModel):
    message:    str = Field(..., description="Motivational sentence, max 18 words.")
    neural_tip: str = Field(..., description="One sentence on cognitive benefit, max 15 words.")


# ─────────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────────

_DIFFICULTY_PROMPT = PromptTemplate(
    input_variables=["game_name", "history_json"],
    template="""You are a cognitive rehabilitation AI. Recommend the optimal difficulty level for the patient's next game session.

Game: {game_name}
Recent session history (most recent last, max 10 entries):
{history_json}

Decision rules:
  • ESCALATE if last 3 sessions avg accuracy > 80% AND avg cog_score > 75
  • DE-ESCALATE if last 2 sessions avg accuracy < 45%
  • Otherwise keep level or increment by 1 maximum
  • Level range is 1–10. Never jump more than 2 levels at once.
  • Goal: keep the patient in a "flow state" — engaged but not overwhelmed

Respond ONLY with valid JSON (no markdown):
{{
  "recommended_level":  <int 1–10>,
  "reasoning":          "<one sentence explaining the choice>",
  "sweet_spot_range":   [<min_int>, <max_int>],
  "should_escalate":    <bool>,
  "should_deescalate":  <bool>
}}"""
)

_FEEDBACK_PROMPT = PromptTemplate(
    input_variables=["game_name", "level", "accuracy", "cog_score", "sessions_played", "trend"],
    template="""You are a warm cognitive rehabilitation coach. The patient just completed a memory game session.

Game: {game_name}
Level reached: {level}
Accuracy: {accuracy}%
Cognitive score: {cog_score}/100
Total sessions this patient has played: {sessions_played}
Recent performance trend: {trend}

Write a brief, warm, encouraging coaching response. Rules:
  • message: 1 sentence, max 18 words, acknowledge their specific performance
  • neural_tip: 1 sentence, max 15 words, one cognitive neuroscience fact about this game type
  • Do NOT say "Great job!" — be more specific and clinical-sounding

Respond ONLY with valid JSON (no markdown):
{{
  "message":    "<feedback sentence>",
  "neural_tip": "<neural benefit sentence>"
}}"""
)


# ─────────────────────────────────────────────────────────────────
# Fallback logic (rule-based, no LLM needed)
# ─────────────────────────────────────────────────────────────────

def _rule_based_difficulty(history: List[Dict]) -> DifficultyRecommendation:
    """Simple rule-based fallback if LLM unavailable."""
    if not history:
        return DifficultyRecommendation(
            recommended_level=1, reasoning="No history — starting at level 1.",
            sweet_spot_range=[1, 3], should_escalate=False, should_deescalate=False,
        )
    last = history[-1]
    current_level = last.get("level_reached", 1)
    recent_acc    = [r.get("accuracy_pct", 50) for r in history[-3:]]
    avg_acc       = sum(recent_acc) / len(recent_acc)

    if avg_acc > 80 and current_level < 10:
        return DifficultyRecommendation(
            recommended_level=min(10, current_level + 1),
            reasoning="Recent accuracy high — escalating difficulty.",
            sweet_spot_range=[current_level, current_level + 2],
            should_escalate=True, should_deescalate=False,
        )
    elif avg_acc < 45 and current_level > 1:
        return DifficultyRecommendation(
            recommended_level=max(1, current_level - 1),
            reasoning="Recent accuracy low — reducing difficulty.",
            sweet_spot_range=[max(1, current_level - 2), current_level],
            should_escalate=False, should_deescalate=True,
        )
    return DifficultyRecommendation(
        recommended_level=current_level,
        reasoning="Performance stable — maintaining current level.",
        sweet_spot_range=[max(1, current_level - 1), min(10, current_level + 1)],
        should_escalate=False, should_deescalate=False,
    )

_FALLBACK_NEURAL_TIPS = {
    "memory_constellation": "Spatial memory tasks strengthen hippocampal-cortical networks.",
    "default": "Repeated cognitive challenges build durable neural connections.",
}


# ─────────────────────────────────────────────────────────────────
# Service class
# ─────────────────────────────────────────────────────────────────

class CognitiveLLM:
    """
    Singleton LangChain pipeline for cognitive game AI.
    """

    def __init__(self):
        api_key    = os.getenv("GOOGLE_API_KEY")
        model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

        if not api_key:
            print("[CognitiveLLM] No GOOGLE_API_KEY — using rule-based fallback.")
            self._llm = None
            return

        self._llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=0.2,
            max_tokens=300,
        )
        _parser = JsonOutputParser()
        self._difficulty_chain = _DIFFICULTY_PROMPT | self._llm | _parser
        self._feedback_chain   = _FEEDBACK_PROMPT   | self._llm | _parser

    # ── Public API ────────────────────────────────────────────────

    async def predict_difficulty(self, game_name: str, history: List[Dict]) -> Dict[str, Any]:
        if not self._llm or len(history) < 2:
            return _rule_based_difficulty(history).model_dump()

        slim_history = [
            {k: v for k, v in r.items()
             if k in ("level_reached", "accuracy_pct", "cog_score", "timestamp")}
            for r in history[-10:]
        ]
        try:
            result = await self._difficulty_chain.ainvoke({
                "game_name":    game_name,
                "history_json": json.dumps(slim_history, indent=2),
            })
            return DifficultyRecommendation(**result).model_dump()
        except Exception as exc:
            print(f"[CognitiveLLM] difficulty prediction failed: {exc}")
            return _rule_based_difficulty(history).model_dump()

    async def generate_feedback(
        self,
        game_name:       str,
        level:           int,
        accuracy:        float,
        cog_score:       float,
        history:         List[Dict],
    ) -> str:
        """Returns a single combined feedback string for the UI."""
        trend = self._compute_trend(history)

        if not self._llm:
            tip = _FALLBACK_NEURAL_TIPS.get(game_name, _FALLBACK_NEURAL_TIPS["default"])
            return f"Every session builds stronger neural connections. {tip}"

        try:
            result = await self._feedback_chain.ainvoke({
                "game_name":       game_name,
                "level":           level,
                "accuracy":        round(accuracy),
                "cog_score":       round(cog_score),
                "sessions_played": len(history),
                "trend":           trend,
            })
            fb = CognitiveFeedback(**result)
            return f"{fb.message} {fb.neural_tip}"
        except Exception as exc:
            print(f"[CognitiveLLM] feedback generation failed: {exc}")
            tip = _FALLBACK_NEURAL_TIPS.get(game_name, _FALLBACK_NEURAL_TIPS["default"])
            return f"Every session builds stronger neural connections. {tip}"

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
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


# Module-level singleton
cognitive_llm = CognitiveLLM()