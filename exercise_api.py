"""
exercise_api.py
===============
FastAPI service that wraps the Nakshatra_v3 exercise scripts.
Exposes HTTP endpoints to start exercise sessions, poll status,
and retrieve results.

Usage:
    python exercise_api.py          # starts on http://0.0.0.0:8001
    python exercise_api.py --port 8002
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent

EXERCISE_REGISTRY = {
    "elbow_stretching": {
        "script": "elbow_stretching.py",
        "display_name": "Elbow Stretching",
        "description": "Left-arm elbow stretching exercise. 3 sets × 10 reps with a 2-second hold.",
        "landmarks": ["left_shoulder", "left_elbow", "left_wrist"],
        "sets": 3,
        "reps_per_set": 10,
        "hold_secs": 2,
    },
    "lateral_raises": {
        "script": "lateral_raises.py",
        "display_name": "Lateral Raises",
        "description": "Left-arm lateral raises. 3 sets × 10 reps — raise arm to shoulder height and hold for 2 seconds.",
        "landmarks": ["left_hip", "left_shoulder", "left_wrist"],
        "sets": 3,
        "reps_per_set": 10,
        "hold_secs": 2,
    },
}

# ──────────────────────────────────────────────────────────────
# In-memory session store
# ──────────────────────────────────────────────────────────────

sessions: dict[str, dict] = {}
# Each session: {
#   "id": str,
#   "exercise": str,
#   "status": "running" | "completed" | "error",
#   "result": dict | None,
#   "error": str | None,
#   "process": subprocess.Popen,
# }


def _run_exercise(session_id: str, exercise_key: str, camera: int):
    """Run an exercise script in a subprocess and parse the JSON result."""
    script_name = EXERCISE_REGISTRY[exercise_key]["script"]
    script_path = SCRIPT_DIR / script_name

    cmd = [sys.executable, str(script_path), "--camera", str(camera)]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(SCRIPT_DIR),
        )
        sessions[session_id]["process"] = proc

        stdout, stderr = proc.communicate()

        # Parse the JSON result from stdout
        result = None
        for line in stdout.splitlines():
            if line.startswith("##RESULT_JSON##"):
                json_str = line[len("##RESULT_JSON##"):]
                result = json.loads(json_str)
                break

        if result:
            sessions[session_id]["status"] = "completed"
            sessions[session_id]["result"] = result
        else:
            sessions[session_id]["status"] = "completed"
            sessions[session_id]["result"] = {
                "exercise": exercise_key,
                "total_reps": 0,
                "avg_peak_angle": 0,
                "sets": [],
                "duration_secs": 0,
                "early_exit": True,
                "note": "No structured result captured — session may have been quit early.",
            }

    except Exception as e:
        sessions[session_id]["status"] = "error"
        sessions[session_id]["error"] = str(e)


# ──────────────────────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────────────────────

app = FastAPI(title="Nakshatra Exercise API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ────────────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    exercise: str
    camera: int = 0


class StartSessionResponse(BaseModel):
    session_id: str
    exercise: str
    status: str


class SessionStatusResponse(BaseModel):
    session_id: str
    exercise: str
    status: str


class SessionResultResponse(BaseModel):
    session_id: str
    exercise: str
    status: str
    result: dict | None = None
    error: str | None = None


# ── Routes ────────────────────────────────────────────────────

@app.get("/exercises")
def list_exercises():
    """Return available exercises (without internal script paths)."""
    return {
        key: {k: v for k, v in info.items() if k != "script"}
        for key, info in EXERCISE_REGISTRY.items()
    }


@app.post("/sessions/start", response_model=StartSessionResponse)
def start_session(req: StartSessionRequest):
    """Launch an exercise session as a subprocess."""
    if req.exercise not in EXERCISE_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unknown exercise: {req.exercise}")

    # Check if there's already a running session
    for sid, sess in sessions.items():
        if sess["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail=f"Session {sid} is already running. Wait for it to finish.",
            )

    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "id": session_id,
        "exercise": req.exercise,
        "status": "running",
        "result": None,
        "error": None,
        "process": None,
    }

    # Launch in a background thread
    thread = threading.Thread(
        target=_run_exercise,
        args=(session_id, req.exercise, req.camera),
        daemon=True,
    )
    thread.start()

    return StartSessionResponse(
        session_id=session_id,
        exercise=req.exercise,
        status="running",
    )


@app.get("/sessions/{session_id}/status", response_model=SessionStatusResponse)
def get_session_status(session_id: str):
    """Check if a session is still running or has completed."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    sess = sessions[session_id]
    return SessionStatusResponse(
        session_id=session_id,
        exercise=sess["exercise"],
        status=sess["status"],
    )


@app.get("/sessions/{session_id}/result", response_model=SessionResultResponse)
def get_session_result(session_id: str):
    """Get the full result of a completed session."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    sess = sessions[session_id]
    return SessionResultResponse(
        session_id=session_id,
        exercise=sess["exercise"],
        status=sess["status"],
        result=sess["result"],
        error=sess["error"],
    )


# ──────────────────────────────────────────────────────────────
# CLI entry
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Nakshatra Exercise API")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8001, help="Bind port")
    args = parser.parse_args()

    print(f"[INFO] Starting Nakshatra Exercise API on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
