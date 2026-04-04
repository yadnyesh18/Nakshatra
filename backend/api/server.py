"""
api/server.py
Single-process FastAPI server:
  - Webcam pose detection in background thread
  - MJPEG video stream  → GET /video_feed
  - SSE live metrics    → GET /events
  - Web dashboard       → GET /
  - Session REST API    → POST /session/start | /session/stop | GET /session/summary
"""

import asyncio
import json
import os
import threading
import time
from logic.llm_orchestrator import get_personalized_physical_feedback,generate_session_report
import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from logic.exercise_classifier import ExerciseClassifier, EXERCISES
from logic.rep_counter import RepCounter
from logic.session import SessionTracker
from logic.body_analyzer import BodyAnalyzer
from pose.pose_detector import PoseDetector

# ── Constants ─────────────────────────────────────────────────────────────────
FONT         = cv2.FONT_HERSHEY_SIMPLEX
GREEN        = (0, 200, 0)
ORANGE       = (0, 165, 255)
RED          = (0, 0, 220)
YELLOW       = (0, 220, 220)
WHITE        = (255, 255, 255)
STATUS_COLOR = {"Correct": GREEN, "Partial": ORANGE, "Incorrect": RED}

_WEB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))

app = FastAPI(title="Rehab Pose Tracker", version="2.0.0")


class _SafeEncoder(json.JSONEncoder):
    """Converts numpy scalars to native Python types for JSON serialisation."""
    def default(self, obj):
        if isinstance(obj, np.integer):  return int(obj)
        if isinstance(obj, np.floating): return float(obj)
        if isinstance(obj, np.ndarray):  return obj.tolist()
        return super().default(obj)


# ── Shared state (protected by lock) ─────────────────────────────────────────
_lock           = threading.Lock()
_latest_jpeg:   bytes = b""
_latest_data:   dict  = {
    "detected": False, "angle": None, "status": None,
    "feedback": "Start a session", "reps": 0,
    "exercise_name": "arm_raise", "metrics": {}
}
_session_running: bool = False

_detector:      PoseDetector | None      = None
_classifier:    ExerciseClassifier | None = None
_rep_counter:   RepCounter | None        = None
_session:       SessionTracker | None    = None
_body_analyzer: BodyAnalyzer | None      = None
_worker_thread: threading.Thread | None  = None


# ── Overlay ───────────────────────────────────────────────────────────────────

def _draw_overlay(frame: np.ndarray, result: dict, rep_state: dict,
                  fps: float, summary: dict, profile=None) -> None:
    h, w      = frame.shape[:2]
    reps      = rep_state.get("reps", 0)
    hold_prog = rep_state.get("hold_progress", 0.0)
    strain_ev = rep_state.get("strain_events", 0)
    rep_st    = rep_state.get("state", "rest")

    # Arm highlight
    if result.get("detected") and len(result.get("arm_points", [])) == 3:
        pts       = result["arm_points"]
        color     = STATUS_COLOR.get(result.get("status", ""), RED)
        thickness = profile.active_thickness if profile else 4
        for i in range(2):
            cv2.line(frame, pts[i], pts[i + 1], color, thickness + 2, cv2.LINE_AA)
        for pt in pts:
            cv2.circle(frame, pt, (profile.joint_radius + 4) if profile else 9,
                       color, -1, cv2.LINE_AA)
            cv2.circle(frame, pt, (profile.joint_radius + 6) if profile else 11,
                       WHITE, 1, cv2.LINE_AA)

    # Angle badge + threshold range
    if result.get("detected") and result.get("angle") is not None:
        mid        = result["arm_points"][1]
        font_scale = max(0.6, min(1.1, profile.torso_height / 280)) if profile and profile.torso_height > 0 else 0.85
        cv2.putText(frame, f"{result['angle']}\xb0",
                    (mid[0] + 14, mid[1] - 14), FONT, font_scale, WHITE, 2, cv2.LINE_AA)
        t_min, t_max = result.get("threshold_min"), result.get("threshold_max")
        if t_min and t_max:
            cv2.putText(frame, f"[{t_min}\xb0-{t_max}\xb0]",
                        (mid[0] + 14, mid[1] + 10), FONT, 0.45, (180, 220, 180), 1, cv2.LINE_AA)

    # Status banner
    color = STATUS_COLOR.get(result.get("status", ""), RED)
    cv2.rectangle(frame, (0, h - 55), (w, h), (20, 20, 20), -1)
    cv2.putText(frame, result.get("feedback", ""), (14, h - 18), FONT, 0.75, color, 2, cv2.LINE_AA)

    # Top-left HUD
    ex_cfg    = EXERCISES.get(result.get("exercise_name", ""), {})
    stage_lbl = result.get("stage_label", "")
    cv2.putText(frame, ex_cfg.get("display_name", ""), (14, 32), FONT, 0.65, WHITE, 2, cv2.LINE_AA)
    if stage_lbl:
        cv2.putText(frame, stage_lbl, (14, 54), FONT, 0.48, (180, 200, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, f"FPS {fps:.0f}", (14, 72), FONT, 0.5, YELLOW, 1, cv2.LINE_AA)

    # Top-right HUD
    cv2.putText(frame, f"Reps: {reps}", (w - 160, 32), FONT, 0.65, GREEN, 2, cv2.LINE_AA)
    cv2.putText(frame, f"Acc: {summary.get('accuracy_pct', 0.0):.0f}%",
                (w - 160, 54), FONT, 0.5, YELLOW, 1, cv2.LINE_AA)
    if strain_ev > 0:
        cv2.putText(frame, f"Strain: {strain_ev}", (w - 160, 72), FONT, 0.5, (0, 0, 255), 1, cv2.LINE_AA)

    # Hold progress bar
    if rep_st == "holding" and hold_prog > 0:
        bar_w = int(w * 0.5)
        bar_x = w // 2 - bar_w // 2
        bar_y = h - 80
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + 14), (40, 40, 40), -1)
        cv2.rectangle(frame, (bar_x, bar_y),
                      (bar_x + int(bar_w * hold_prog), bar_y + 14), GREEN, -1)
        cv2.putText(frame, f"Hold... {int(hold_prog * 100)}%",
                    (bar_x, bar_y - 4), FONT, 0.5, WHITE, 1, cv2.LINE_AA)

    # Strain flash border
    if result.get("strain_warning"):
        cv2.rectangle(frame, (0, 0), (w, h), (0, 0, 220), 6)


# ── Camera worker ─────────────────────────────────────────────────────────────

def _camera_worker(exercise: str, camera_index: int = 0, stage: int = 0) -> None:
    global _latest_jpeg, _latest_data, _session_running
    global _detector, _classifier, _rep_counter, _session, _body_analyzer

    _detector      = PoseDetector()
    _classifier    = ExerciseClassifier(exercise, stage=stage)
    _rep_counter   = RepCounter(hold_sec=_classifier.config.get("hold_sec", 2))
    _session       = SessionTracker(exercise, stage=stage)
    _body_analyzer = BodyAnalyzer(calib_frames=30)

    cap = cv2.VideoCapture(camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    prev_time = time.time()

    while True:
        with _lock:
            if not _session_running:
                break

        ok, frame = cap.read()
        if not ok:
            time.sleep(0.01)
            continue

        frame     = cv2.flip(frame, 1)
        mp_result = _detector.detect(frame)

        if mp_result.pose_landmarks:
            lms     = mp_result.pose_landmarks[0]
            profile = _body_analyzer.update(lms, frame.shape)
            result  = _classifier.classify(lms, frame.shape, profile)
            _detector.draw_skeleton(frame, lms, profile=profile,
                                    active_indices=result.get("active_indices", set()))
        else:
            profile = _body_analyzer.profile
            result  = {
                "detected": False, "angle": None, "status": None,
                "feedback": "No person detected", "arm_points": [],
                "exercise_name": exercise, "active_indices": set(),
                "threshold_min": None, "threshold_max": None,
                "strain_warning": False, "stage_label": "",
            }

        strain    = result.get("strain_warning", False)
        rep_state = _rep_counter.update(result.get("status") or "", strain)
        _session.update(result["angle"], result["status"], rep_state)
        summary   = _session.get_summary()

        now       = time.time()
        fps       = 1.0 / max(now - prev_time, 1e-6)
        prev_time = now

        _draw_overlay(frame, result, rep_state, fps, summary, profile)

        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])

        body_info = {
            "calibrated":    profile.calibrated,
            "body_label":    profile.body_label,
            "shoulder_type": profile.shoulder_type,
            "limb_type":     profile.limb_type,
            "angle_offset":  round(profile.angle_offset, 1),
            "rom_offset":    round(getattr(profile, "rom_offset", 0.0), 1),
            "frames_seen":   profile.frames_seen,
        } if profile else {}

        with _lock:
            _latest_jpeg = jpeg.tobytes()
            _latest_data = {
                **result,
                "active_indices": [int(i) for i in result.get("active_indices", set())],
                "reps":           rep_state["reps"],
                "hold_progress":  rep_state["hold_progress"],
                "rep_state":      rep_state["state"],
                "strain_events":  rep_state["strain_events"],
                "metrics":        summary,
                "body_info":      body_info,
            }

    cap.release()
    with _lock:
        _latest_jpeg = b""


# ── REST endpoints ────────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    exercise: str = "arm_raise"
    camera:   int = 0
    stage:    int = 0


@app.post("/session/start")
def start_session(body: StartRequest):
    global _session_running, _worker_thread

    if body.exercise not in EXERCISES:
        raise HTTPException(400, f"Unknown exercise. Available: {list(EXERCISES.keys())}")

    with _lock:
        _session_running = False
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=2.0)

    with _lock:
        _session_running = True

    _worker_thread = threading.Thread(
        target=_camera_worker,
        args=(body.exercise, body.camera, body.stage),
        daemon=True
    )
    _worker_thread.start()
    return {"status": "started", "exercise": body.exercise, "config": EXERCISES[body.exercise]}


@app.post("/session/stop")
def stop_session():
    global _session_running
    with _lock:
        _session_running = False

    summary, log_path = {}, ""
    if _session:
        summary  = _session.get_summary()
        log_path = _session.save()
    return {"status": "stopped", "summary": summary, "saved_to": log_path}


@app.get("/session/summary")
def session_summary():
    if _session is None:
        raise HTTPException(400, "No active session.")
    return {"summary": _session.get_summary()}


@app.get("/exercises")
def list_exercises():
    return {"exercises": EXERCISES}


# ── MJPEG stream ──────────────────────────────────────────────────────────────

def _mjpeg_generator():
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(blank, "Start a session to begin", (80, 240), FONT, 0.8, WHITE, 2, cv2.LINE_AA)
    _, blank_jpeg = cv2.imencode(".jpg", blank)
    blank_bytes   = blank_jpeg.tobytes()

    while True:
        with _lock:
            data = _latest_jpeg if _latest_jpeg else blank_bytes
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
        time.sleep(0.033)


@app.get("/video_feed")
def video_feed():
    return StreamingResponse(_mjpeg_generator(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


# ── SSE stream ────────────────────────────────────────────────────────────────

@app.get("/events")
async def sse_events(request: Request):
    async def generator():
        while True:
            if await request.is_disconnected():
                break
            with _lock:
                payload = json.dumps(_latest_data, cls=_SafeEncoder)
            yield {"data": payload}
            await asyncio.sleep(0.1)
    return EventSourceResponse(generator())

class CoachRequest(BaseModel):
    exercise: str
    reps: int
    avg_angle: float
    strain_events: int

# ── AI Coaching ────────────────────────────────────────────────────────────── 
@app.post("/session/coach")
def get_ai_coaching(body: CoachRequest):
    """
    The frontend calls this whenever it wants real-time feedback (e.g., every 5 reps).
    It uses Gemini to generate a fast, motivational correction.
    """
    try:
        # We format the 'form issues' based on the strain events detected by your BodyAnalyzer
        issues = f"Patient had {body.strain_events} strain events." if body.strain_events > 0 else "None"
        
        # Safely extract the target angle from the EXERCISES dictionary
        exercise_config = EXERCISES.get(body.exercise, {})
        stages = exercise_config.get("stages", [{}])
        
        # Safely get correct_max from the first stage, fallback to 180
        target = stages.get("correct_max", 180) if stages else 180
        
        feedback = generate_live_physical_feedback(
            exercise=body.exercise,
            target=int(target),
            achieved=int(body.avg_angle),
            issues=issues
        )
        return {"coach_feedback": feedback}
    except Exception as e:
        # It is helpful to print the error to the terminal during the hackathon so you know WHY it failed
        print(f"Coach endpoint error: {e}") 
        return {"coach_feedback": "Keep up the good work! Focus on your form."}

# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    with open(os.path.join(_WEB_DIR, "index.html"), "r") as f:
        html = f.read()

    ui_exercises = {
        k: {
            "display_name":  v["display_name"],
            "description":   v.get("description", ""),
            "hold_sec":      v.get("hold_sec", 0),
            "correct_min":   v["stages"][0]["correct_min"],
            "correct_max":   v["stages"][0]["correct_max"],
            "partial_range": v["stages"][0]["partial_range"],
            "stages": [
                {"label": s["label"], "correct_min": s["correct_min"], "correct_max": s["correct_max"]}
                for s in v["stages"]
            ],
        }
        for k, v in EXERCISES.items()
    }

    injection = f"<script>window.__EXERCISES__ = {json.dumps(ui_exercises)};</script>"
    html = html.replace("<body>", "<body>\n" + injection, 1)

    return Response(content=html, media_type="text/html",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate",
                             "Pragma": "no-cache"})
