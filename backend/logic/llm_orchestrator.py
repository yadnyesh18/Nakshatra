"""
logic/llm_orchestrator.py
==========================
Hybrid Edge-Cloud LLM Orchestration Layer for Nakshatra Neuro-Rehab System.

Architecture:
  - REAL-TIME PATH  : Google Gemini (Flash) → sub-second motivational/corrective cues
  - ASYNC PATH      : Local Ollama/Qwen     → end-of-day clinical report generation
  - MEMORY LAYER    : Supabase pgvector     → patient-personalised baseline retrieval (RAG)

Usage (from api/server.py):
    from logic.llm_orchestrator import (
        get_personalized_physical_feedback,
        evaluate_cognitive_memory,
        generate_session_report,
        store_patient_baseline,
    )
"""

# ──────────────────────────────────────────────────────────────────────────────
# Standard library & third-party imports
# ──────────────────────────────────────────────────────────────────────────────

import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError

# LangChain core
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import PromptTemplate

# LangChain model integrations
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    _GEMINI_IMPORT_OK = True
except ImportError:
    _GEMINI_IMPORT_OK = False

try:
    from langchain_community.llms import Ollama
    _OLLAMA_IMPORT_OK = True
except ImportError:
    _OLLAMA_IMPORT_OK = False

# Supabase (pgvector for RAG)
try:
    from supabase import create_client, Client as SupabaseClient
    _SUPABASE_IMPORT_OK = True
except ImportError:
    _SUPABASE_IMPORT_OK = False

# Google Generative AI embeddings (for baseline vectorisation)
try:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    _EMBEDDINGS_IMPORT_OK = True
except ImportError:
    _EMBEDDINGS_IMPORT_OK = False


# ──────────────────────────────────────────────────────────────────────────────
# Environment & logging setup
# ──────────────────────────────────────────────────────────────────────────────

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Network config — replace with the actual IP of your Ollama host (MacBook M4)
OLLAMA_HOST_IP: str = os.getenv("OLLAMA_HOST_IP", "[IP_ADDRESS]")
OLLAMA_PORT:    str = os.getenv("OLLAMA_PORT", "11434")
OLLAMA_MODEL:   str = os.getenv("OLLAMA_MODEL", "qwen2.5")

GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")

SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_TABLE: str = "patient_baselines"   # table that stores embeddings


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic output schemas  (AI responses are ONLY accepted if they match)
# ──────────────────────────────────────────────────────────────────────────────

class PhysicalFeedbackOutput(BaseModel):
    """Real-time motivational / corrective feedback for a physical therapy rep."""
    message:   str   = Field(..., description="Single encouraging/corrective sentence for the patient.")
    alert:     bool  = Field(False, description="True if the patient is at risk of injury.")
    delta_pct: float = Field(0.0, description="How close the patient is to their personal baseline (0–100%).")


class CognitiveFeedbackOutput(BaseModel):
    """Structured result of a cognitive memory recall test."""
    score:         int  = Field(..., ge=0, le=100, description="Memory recall score out of 100.")
    words_recalled: list[str] = Field(default_factory=list, description="Words the patient correctly recalled.")
    feedback:      str  = Field(..., description="Short encouraging message for the patient.")
    difficulty_up: bool = Field(False, description="True if the system should increase word-list difficulty next round.")


class ClinicalReportOutput(BaseModel):
    """End-of-day clinical summary destined for the treating physician."""
    patient_session_id: str   = Field(..., description="Unique identifier for the session log.")
    overall_score:      float = Field(..., ge=0.0, le=100.0, description="Composite session performance score.")
    physical_summary:   str   = Field(..., description="Clinical narrative for physical performance.")
    cognitive_summary:  str   = Field(..., description="Clinical narrative for cognitive performance.")
    recommendations:    list[str] = Field(default_factory=list, description="Actionable clinical recommendations.")
    red_flags:          list[str] = Field(default_factory=list, description="Symptoms or metrics that require urgent review.")


# ──────────────────────────────────────────────────────────────────────────────
# Singleton model initialisation — failures are logged, not raised
# ──────────────────────────────────────────────────────────────────────────────

_gemini_llm:       Any = None
_gemini_embedder:  Any = None
_ollama_llm:       Any = None
_supabase_client:  Any = None


def _init_gemini() -> None:
    """Initialise Google Gemini Flash (real-time, low-latency path)."""
    global _gemini_llm
    if not _GEMINI_IMPORT_OK:
        log.warning("langchain-google-genai not installed. Gemini unavailable.")
        return
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        log.warning("GOOGLE_API_KEY not set. Gemini will use fallback responses.")
        return
    try:
        _gemini_llm = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            temperature=0.25,           # Low temp → consistent, factual medical cues
            google_api_key=api_key,
            convert_system_message_to_human=True,
        )
        log.info("✅ Gemini LLM initialised (model: %s).", GEMINI_MODEL)
    except Exception as exc:
        log.error("❌ Gemini init failed: %s", exc)


def _init_embedder() -> None:
    """Initialise Google embeddings for Supabase pgvector storage."""
    global _gemini_embedder
    if not _EMBEDDINGS_IMPORT_OK:
        return
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return
    try:
        _gemini_embedder = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=api_key,
        )
        log.info("✅ Google Embeddings initialised.")
    except Exception as exc:
        log.error("❌ Embedder init failed: %s", exc)


def _init_ollama() -> None:
    """Initialise local Ollama/Qwen (privacy-first async clinical path)."""
    global _ollama_llm
    if not _OLLAMA_IMPORT_OK:
        log.warning("langchain-community not installed. Ollama unavailable.")
        return
    try:
        _ollama_llm = Ollama(
            base_url=f"http://{OLLAMA_HOST_IP}:{OLLAMA_PORT}",
            model=OLLAMA_MODEL,
            timeout=120,       # Clinical reports can be long; allow generous time
        )
        log.info("✅ Ollama LLM configured (host: %s, model: %s).", OLLAMA_HOST_IP, OLLAMA_MODEL)
    except Exception as exc:
        log.error("❌ Ollama init failed: %s", exc)


def _init_supabase() -> None:
    """Initialise Supabase client for pgvector RAG operations."""
    global _supabase_client
    if not _SUPABASE_IMPORT_OK:
        log.warning("supabase-py not installed. RAG personalisation unavailable.")
        return
    if not SUPABASE_URL or not SUPABASE_KEY:
        log.warning("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set in .env.")
        return
    try:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        log.info("✅ Supabase client initialised.")
    except Exception as exc:
        log.error("❌ Supabase init failed: %s", exc)


# Run all initialisations at import time (FastAPI startup)
_init_gemini()
_init_embedder()
_init_ollama()
_init_supabase()


# ──────────────────────────────────────────────────────────────────────────────
# RAG helpers — Supabase pgvector baseline storage & retrieval
# ──────────────────────────────────────────────────────────────────────────────

def store_patient_baseline(patient_id: str, baseline_data: dict) -> bool:
    """
    RAG Engineer: Embed a patient's initial calibration data and upsert it into
    Supabase's `patient_baselines` table for later personalised retrieval.

    Args:
        patient_id:    Unique patient identifier (UUID or short code).
        baseline_data: Dict containing calibration key-value pairs, e.g.
                       {"max_painless_angle": 95, "baseline_reaction_time_ms": 420,
                        "dominant_arm": "right", "pain_threshold_note": "..."}

    Returns:
        True on success, False on failure (never raises).
    """
    if not _supabase_client:
        log.error("store_patient_baseline: Supabase not available.")
        return False
    if not _gemini_embedder:
        log.error("store_patient_baseline: Embedder not available.")
        return False

    try:
        # Serialise the baseline dict to a natural-language string for embedding
        baseline_text = (
            f"Patient baseline calibration for {patient_id}: "
            + "; ".join(f"{k}={v}" for k, v in baseline_data.items())
        )
        embedding_vector = _gemini_embedder.embed_query(baseline_text)

        payload = {
            "patient_id":    patient_id,
            "baseline_text": baseline_text,
            "baseline_data": json.dumps(baseline_data),   # store raw JSON too
            "embedding":     embedding_vector,
        }

        # Upsert so re-calibration overwrites the previous baseline
        _supabase_client.table(SUPABASE_TABLE).upsert(
            payload, on_conflict="patient_id"
        ).execute()

        log.info("✅ Baseline stored for patient %s.", patient_id)
        return True
    except Exception as exc:
        log.error("❌ Failed to store baseline for %s: %s", patient_id, exc)
        return False


def _retrieve_patient_baseline(patient_id: str) -> dict:
    """
    RAG Engineer (private helper): Fetch a patient's baseline calibration
    from Supabase using exact patient_id lookup (pgvector similarity search
    is used for future multi-patient scenario matching; for now, direct FK).

    Returns the baseline_data dict, or an empty dict if not found.
    """
    if not _supabase_client:
        return {}
    try:
        response = (
            _supabase_client.table(SUPABASE_TABLE)
            .select("baseline_data")
            .eq("patient_id", patient_id)
            .limit(1)
            .execute()
        )
        if response.data:
            return json.loads(response.data[0]["baseline_data"])
        log.warning("No baseline found for patient %s. Using generic defaults.", patient_id)
        return {}
    except Exception as exc:
        log.error("❌ Baseline retrieval error for %s: %s", patient_id, exc)
        return {}


# ──────────────────────────────────────────────────────────────────────────────
# ROUTE 1 — Real-Time Physical Feedback (Gemini + RAG personalisation)
# ──────────────────────────────────────────────────────────────────────────────

_PHYSICAL_FEEDBACK_PROMPT = PromptTemplate.from_template(
    """You are an AI neuro-rehabilitation assistant providing real-time coaching.

=== PATIENT PERSONALISED BASELINE (retrieved from clinical calibration) ===
{baseline_context}

=== CURRENT REP DATA ===
Exercise:       {exercise_name}
Target Angle:   {target_angle}°
Achieved Angle: {achieved_angle}°
Repetitions completed this set: {reps}
Form issues:    {form_issues}

=== TASK ===
Compare the achieved angle against the patient's PERSONAL MAXIMUM documented above.
Give ONE short, direct, motivating sentence for the patient (≤ 20 words).
If the form issue is serious or they are nearing their documented pain threshold, set "alert" to true.
Calculate "delta_pct" as: (achieved_angle / patient_max_angle * 100), clamped to [0, 100].
If no personalised max is known, assume the target angle is the reference.

Return ONLY valid JSON that exactly matches this schema — no markdown fences:
{{
  "message":   "<string>",
  "alert":     <true|false>,
  "delta_pct": <float 0-100>
}}"""
)

# Hard-coded fallback for network/rate-limit failures — keeps the demo alive
_PHYSICAL_FEEDBACK_FALLBACK = PhysicalFeedbackOutput(
    message="Great effort! Keep pushing through the movement.",
    alert=False,
    delta_pct=0.0,
)


def get_personalized_physical_feedback(
    patient_id:     str,
    exercise_name:  str,
    target_angle:   float,
    achieved_angle: float,
    reps:           int  = 0,
    form_issues:    str  = "None detected",
) -> PhysicalFeedbackOutput:
    """
    Agent Architect / RAG Engineer:
    1. Retrieves patient baseline from Supabase pgvector.
    2. Injects it into the Gemini prompt (RAG augmentation).
    3. Gets a real-time corrective/motivational response.
    4. Validates the JSON output against PhysicalFeedbackOutput schema.

    Called by api/server.py during the live webcam loop (target: <500 ms).

    Returns:
        PhysicalFeedbackOutput — always (never raises).
    """
    # ── Step 1: RAG — personalise with patient baseline ──────────────────────
    baseline = _retrieve_patient_baseline(patient_id)
    if baseline:
        baseline_context = (
            f"Max painless angle documented at calibration: {baseline.get('max_painless_angle', 'unknown')}°. "
            f"Pain threshold note: {baseline.get('pain_threshold_note', 'none')}. "
            f"Baseline reaction time: {baseline.get('baseline_reaction_time_ms', 'unknown')} ms. "
            f"Dominant arm: {baseline.get('dominant_arm', 'unknown')}."
        )
    else:
        baseline_context = "No personalised baseline on file. Provide generic encouragement."

    # ── Step 2: Route to Gemini ──────────────────────────────────────────────
    if not _gemini_llm:
        log.warning("Gemini unavailable — returning physical feedback fallback.")
        return _PHYSICAL_FEEDBACK_FALLBACK

    try:
        # LangChain LCEL chain: prompt → Gemini → raw string → parse JSON
        chain = _PHYSICAL_FEEDBACK_PROMPT | _gemini_llm | StrOutputParser()
        raw_response: str = chain.invoke({
            "baseline_context": baseline_context,
            "exercise_name":    exercise_name,
            "target_angle":     target_angle,
            "achieved_angle":   achieved_angle,
            "reps":             reps,
            "form_issues":      form_issues,
        })

        # ── Step 3: Parse and validate output with Pydantic ─────────────────
        # Strip potential markdown code blocks the model may add
        raw_json = raw_response.strip().lstrip("```json").rstrip("```").strip()
        parsed   = PhysicalFeedbackOutput(**json.loads(raw_json))
        return parsed

    except (json.JSONDecodeError, ValidationError) as parse_err:
        log.error("Physical feedback JSON parse error: %s | raw: %s", parse_err, raw_response[:200])
        # Graceful degradation: return fallback rather than crashing
        return _PHYSICAL_FEEDBACK_FALLBACK

    except Exception as exc:
        log.error("Physical feedback Gemini call failed: %s", exc)
        return _PHYSICAL_FEEDBACK_FALLBACK


# ──────────────────────────────────────────────────────────────────────────────
# ROUTE 2 — Cognitive Memory Evaluation (Gemini)
# ──────────────────────────────────────────────────────────────────────────────

_COGNITIVE_EVAL_PROMPT = PromptTemplate.from_template(
    """You are a cognitive rehabilitation AI evaluating a patient's short-term memory recall.

Target words the patient was asked to memorise: {target_words}
Patient's transcribed verbal response (via ASR): "{patient_response}"

Score the recall objectively:
  - Each correctly recalled word (exact or phonetically close) = (100 / total_words) points.
  - Assign a score 0–100.
  - List only the words the patient actually recalled.
  - Suggest increasing difficulty ("difficulty_up": true) if score > 85.

Return ONLY valid JSON — no markdown fences:
{{
  "score":          <int 0-100>,
  "words_recalled": ["<word>", ...],
  "feedback":       "<one encouraging sentence for the patient>",
  "difficulty_up":  <true|false>
}}"""
)

_COGNITIVE_EVAL_FALLBACK = CognitiveFeedbackOutput(
    score=0,
    words_recalled=[],
    feedback="Session evaluation unavailable right now. Keep practising!",
    difficulty_up=False,
)


def evaluate_cognitive_memory(
    target_words:     list[str],
    patient_response: str,
) -> CognitiveFeedbackOutput:
    """
    LLM Application Developer:
    Called by api/server.py after Sarvam AI transcribes the patient's verbal input.
    Routes to Gemini for structured memory-recall evaluation.

    Args:
        target_words:     List of words the patient was asked to remember.
        patient_response: Transcribed speech from Sarvam AI.

    Returns:
        CognitiveFeedbackOutput — always (never raises).
    """
    if not _gemini_llm:
        log.warning("Gemini unavailable — returning cognitive eval fallback.")
        return _COGNITIVE_EVAL_FALLBACK

    words_str = ", ".join(target_words)

    try:
        chain = _COGNITIVE_EVAL_PROMPT | _gemini_llm | StrOutputParser()
        raw_response: str = chain.invoke({
            "target_words":     words_str,
            "patient_response": patient_response,
        })

        raw_json = raw_response.strip().lstrip("```json").rstrip("```").strip()
        parsed   = CognitiveFeedbackOutput(**json.loads(raw_json))
        return parsed

    except (json.JSONDecodeError, ValidationError) as parse_err:
        log.error("Cognitive eval JSON parse error: %s | raw: %s", parse_err, raw_response[:200])
        return _COGNITIVE_EVAL_FALLBACK

    except Exception as exc:
        log.error("Cognitive eval Gemini call failed: %s", exc)
        return _COGNITIVE_EVAL_FALLBACK


# ──────────────────────────────────────────────────────────────────────────────
# ROUTE 3 — Secure End-of-Day Clinical Report (Ollama / Qwen — local)
# ──────────────────────────────────────────────────────────────────────────────

_CLINICAL_REPORT_PROMPT = PromptTemplate.from_template(
    """You are an expert clinical AI assistant specialising in neuro-rehabilitation.
A physical therapist has requested an end-of-day session report for a treating physician.

=== SESSION LOG (JSON) ===
{session_log_json}

=== TASK ===
Analyse ALL physical and cognitive metrics in the session log.
Generate a comprehensive, medically precise clinical summary.
Identify any red flags (e.g., severe angle regression, low recall scores, fatigue indicators).
Provide 2–5 specific, actionable clinical recommendations.

Return ONLY valid JSON — no markdown fences — matching this schema exactly:
{{
  "patient_session_id": "<string>",
  "overall_score":      <float 0–100>,
  "physical_summary":   "<clinical narrative>",
  "cognitive_summary":  "<clinical narrative>",
  "recommendations":    ["<string>", ...],
  "red_flags":          ["<string>", ...]
}}"""
)

_CLINICAL_REPORT_FALLBACK = json.dumps({
    "patient_session_id": "UNAVAILABLE",
    "overall_score":      0.0,
    "physical_summary":   "Clinical report generation failed. Local privacy model offline.",
    "cognitive_summary":  "Please review the raw session log manually.",
    "recommendations":    ["Review session data manually with the treating physician."],
    "red_flags":          ["Automated analysis unavailable — manual review required."],
})


def generate_session_report(session_log: dict) -> str:
    """
    Agent Architect / Data Engineer:
    Routes the end-of-day session log to the LOCAL Ollama/Qwen instance for
    a fully private, HIPAA-conscious clinical report. Never sends this data
    to an external cloud service.

    Args:
        session_log: Full session dict from SessionTracker.get_summary(), e.g.:
                     {"session_id": "...", "exercise": "arm_raise",
                      "total_reps": 35, "accuracy_pct": 78.5,
                      "cognitive_rounds": [...], ...}

    Returns:
        Raw JSON string of ClinicalReportOutput (or the fallback JSON string).
        The caller (api/server.py) can json.loads() this for the response.
    """
    if not _ollama_llm:
        log.error("Local Ollama model offline — returning clinical report fallback.")
        return _CLINICAL_REPORT_FALLBACK

    try:
        session_log_json = json.dumps(session_log, indent=2)

        # LangChain LCEL: prompt → local Ollama/Qwen → string output
        chain = _CLINICAL_REPORT_PROMPT | _ollama_llm | StrOutputParser()
        raw_response: str = chain.invoke({"session_log_json": session_log_json})

        # Strip any markdown fences the model may have added
        raw_json = raw_response.strip().lstrip("```json").rstrip("```").strip()

        # Validate with Pydantic before returning — ensures schema integrity
        validated = ClinicalReportOutput(**json.loads(raw_json))
        log.info("✅ Clinical report generated for session %s.", validated.patient_session_id)
        return validated.model_dump_json(indent=2)

    except (json.JSONDecodeError, ValidationError) as parse_err:
        log.error("Clinical report JSON parse error: %s | raw: %s", parse_err, raw_response[:300])
        # Inject the raw text as the physical_summary for the physician to read
        fallback_dict = json.loads(_CLINICAL_REPORT_FALLBACK)
        fallback_dict["physical_summary"] = (
            f"Automated parsing failed. Raw model output: {raw_response[:500]}"
        )
        return json.dumps(fallback_dict, indent=2)

    except Exception as exc:
        log.error("Clinical report generation failed: %s", exc)
        return _CLINICAL_REPORT_FALLBACK


# ──────────────────────────────────────────────────────────────────────────────
# Health-check helper (useful for /api/health endpoint in server.py)
# ──────────────────────────────────────────────────────────────────────────────

def get_orchestrator_status() -> dict:
    """
    Returns the connectivity status of all three AI sub-systems.
    Wire this into a GET /api/health endpoint for live-demo monitoring.
    """
    return {
        "gemini_realtime":   _gemini_llm is not None,
        "ollama_local":      _ollama_llm is not None,
        "supabase_rag":      _supabase_client is not None,
        "embedder_ready":    _gemini_embedder is not None,
        "ollama_host":       f"http://{OLLAMA_HOST_IP}:{OLLAMA_PORT}",
        "ollama_model":      OLLAMA_MODEL,
        "gemini_model":      GEMINI_MODEL,
    }   