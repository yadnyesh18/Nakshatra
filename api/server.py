"""
api/server.py
Single-process FastAPI server that:
  - Runs MediaPipe pose detection on the webcam
  - Streams annotated MJPEG video  →  GET /video_feed
  - Streams live JSON metrics (SSE) →  GET /events
  - Serves the web dashboard        →  GET /
  - REST session control            →  POST /session/start | GET /session/summary

One command starts everything:
    uvicorn api.server:app --host 0.0.0.0 --port 8000
"""

import asyncio
import base64
import json
import os
import threading
import time

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from logic.exercise_classifier import ExerciseClassifier, EXERCISES
from logic.rep_counter import RepCounter
from logic.session import SessionTracker
from pose.pose_detector import PoseDetector

# ── Constants ─────────────────────────────────────────────────────────────────
FONT      = cv2.FONT_HERSHEY_SIMPLEX
GREEN     = (0, 200, 0)
ORANGE    = (0, 165, 255)
RED       = (0, 0, 220)
YELLOW    = (0, 220, 220)
WHITE     = (255, 255, 255)
ARM_COLOR = (255, 140, 0)
STATUS_COLOR = {"Correct": GREEN, "Partial": ORANGE, "Incorrect": RED}

_WEB_DIR = os.path.join(os.path.dirname(__file__), "..", "web")

app = FastAPI(title="Rehab Pose Tracker", version="2.0.0")

# ── Shared state (protected by lock) ─────────────────────────────────────────
_lock = threading.Lock()
_latest_jpeg: bytes = b""
_latest_data: dict = {
    "detected": False, "angle": None, "status": None,
    "feedback": "Start a session", "reps": 0,
    "exercise_name": "arm_raise", "metrics": {}
}
_active_exercise: str = "arm_raise"
_session_running: bool = False

# Module-level singletons (re-created on session start)
_detector:    PoseDetector | None = None
_classifier:  ExerciseClassifier | None = None
_rep_counter: RepCounter | None = None
_session:     SessionTracker | None = None
_cap:         cv2.VideoCapture | None = None
_worker_thread: threading.Thread | None = None


# ── Overlay drawing ───────────────────────────────────────────────────────────

def _draw_overlay(frame: np.ndarray, result: dict, reps: int,
                  fps: float, summary: dict) -> None:
    h, w = frame.shape[:2]

    # Arm highlight
    if result.get("detected") and len(result.get("arm_points", [])) == 3:
        pts = result["arm_points"]
        for i in range(2):
            cv2.line(frame, pts[i], pts[i + 1], ARM_COLOR, 4, cv2.LINE_AA)
        for pt in pts:
            cv2.circle(frame, pt, 9, ARM_COLOR, -1, cv2.LINE_AA)

    # Angle badge
    if result.get("detected") and result.get("angle") is not None:
        mid = result["arm_points"][1]
        cv2.putText(frame, f"{result['angle']}\xb0",
                    (mid[0] + 14, mid[1] - 14), FONT, 0.85, WHITE, 2, cv2.LINE_AA)

    # Status banner
    color = STATUS_COLOR.get(result.get("status", ""), RED)
    cv2.rectangle(frame, (0, h - 55), (w, h), (20, 20, 20), -1)
    cv2.putText(frame, result.get("feedback", ""), (14, h - 18),
                FONT, 0.75, color, 2, cv2.LINE_AA)

    # HUD top-left
    ex_cfg = EXERCISES.get(result.get("exercise_name", ""), {})
    cv2.putText(frame, ex_cfg.get("display_name", ""), (14, 32),
                FONT, 0.65, WHITE, 2, cv2.LINE_AA)
    cv2.putText(frame, f"FPS {fps:.0f}", (14, 58), FONT, 0.6, YELLOW, 2, cv2.LINE_AA)

    # HUD top-right
    cv2.putText(frame, f"Reps: {reps}", (w - 160, 32), FONT, 0.65, GREEN, 2, cv2.LINE_AA)
    acc = summary.get("accuracy_pct", 0.0)
    cv2.putText(frame, f"Acc: {acc:.0f}%", (w - 160, 58), FONT, 0.6, YELLOW, 2, cv2.LINE_AA)


# ── Background webcam worker ──────────────────────────────────────────────────

def _camera_worker(exercise: str, camera_index: int = 0) -> None:
    """
    Runs in a daemon thread.
    Captures frames, runs pose detection, updates shared state.
    """
    global _latest_jpeg, _latest_data, _session_running
    global _detector, _classifier, _rep_counter, _session, _cap

    _detector    = PoseDetector()
    _classifier  = ExerciseClassifier(exercise)
    _rep_counter = RepCounter()
    _session     = SessionTracker(exercise)

    cap = cv2.VideoCapture(camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    with _lock:
        _cap = cap

    prev_time = time.time()

    while True:
        with _lock:
            running = _session_running
        if not running:
            break

        ok, frame = cap.read()
        if not ok:
            time.sleep(0.01)
            continue

        frame = cv2.flip(frame, 1)

        mp_result = _detector.detect(frame)

        if mp_result.pose_landmarks:
            _detector.draw_skeleton(frame, mp_result.pose_landmarks[0])
            result = _classifier.classify(mp_result.pose_landmarks[0], frame.shape)
        else:
            result = {
                "detected": False, "angle": None, "status": None,
                "feedback": "No person detected", "arm_points": [],
                "exercise_name": exercise
            }

        reps = _rep_counter.update(result.get("status") or "")
        _session.update(result["angle"], result["status"], reps)
        summary = _session.get_summary()

        now = time.time()
        fps = 1.0 / max(now - prev_time, 1e-6)
        prev_time = now

        _draw_overlay(frame, result, reps, fps, summary)

        _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])

        with _lock:
            _latest_jpeg = jpeg.tobytes()
            _latest_data = {
                **result,
                "reps":    reps,
                "metrics": summary,
            }

    cap.release()
    with _lock:
        _latest_jpeg = b""


# ── REST endpoints ────────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    exercise: str = "arm_raise"
    camera: int = 0


@app.post("/session/start")
def start_session(body: StartRequest):
    global _session_running, _worker_thread, _active_exercise

    if body.exercise not in EXERCISES:
        raise HTTPException(400, f"Unknown exercise. Available: {list(EXERCISES.keys())}")

    # Stop existing session
    with _lock:
        _session_running = False

    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=2.0)

    _active_exercise = body.exercise
    with _lock:
        _session_running = True

    _worker_thread = threading.Thread(
        target=_camera_worker,
        args=(body.exercise, body.camera),
        daemon=True
    )
    _worker_thread.start()

    return {"status": "started", "exercise": body.exercise,
            "config": EXERCISES[body.exercise]}


@app.post("/session/stop")
def stop_session():
    global _session_running
    with _lock:
        _session_running = False
        running = _session_running

    summary = {}
    log_path = ""
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


# ── MJPEG video stream ────────────────────────────────────────────────────────

def _mjpeg_generator():
    """Yield MJPEG frames from the shared buffer."""
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(blank, "Start a session to begin", (80, 240),
                FONT, 0.8, WHITE, 2, cv2.LINE_AA)
    _, blank_jpeg = cv2.imencode(".jpg", blank)
    blank_bytes = blank_jpeg.tobytes()

    while True:
        with _lock:
            data = _latest_jpeg if _latest_jpeg else blank_bytes
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n")
        time.sleep(0.033)   # ~30 fps cap


@app.get("/video_feed")
def video_feed():
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# ── SSE live data stream ──────────────────────────────────────────────────────

@app.get("/events")
async def sse_events(request):
    """Server-Sent Events — pushes live JSON metrics to the browser."""
    async def generator():
        while True:
            if await request.is_disconnected():
                break
            with _lock:
                payload = json.dumps(_latest_data)
            yield {"data": payload}
            await asyncio.sleep(0.1)   # 10 Hz is plenty for UI updates

    return EventSourceResponse(generator())


# ── Serve web dashboard ───────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """
    Serve the dashboard with exercises injected server-side.
    Exercises are embedded as a JS variable — no fetch needed in the browser.
    Cache-Control headers prevent stale HTML from being served.
    """
    index = os.path.join(_WEB_DIR, "index.html")
    with open(index, "r") as f:
        html = f.read()

    # Strip landmarks — browser only needs display fields
    ui_exercises = {
        k: {
            "display_name":  v["display_name"],
            "correct_min":   v["correct_min"],
            "correct_max":   v["correct_max"],
            "partial_range": v["partial_range"],
        }
        for k, v in EXERCISES.items()
    }

    # Inject as the FIRST script inside <body> so it runs before anything else
    injection = f"<script>window.__EXERCISES__ = {json.dumps(ui_exercises)};</script>"
    html = html.replace("<body>", "<body>\n" + injection, 1)

    return Response(
        content=html,
        media_type="text/html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma":        "no-cache",
        },
    )
