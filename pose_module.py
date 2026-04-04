"""
pose_module.py
Core AI module for rehabilitation pose tracking using MediaPipe Tasks API.
Tracks shoulder–elbow–wrist angle and classifies posture in real time.
Compatible with mediapipe >= 0.10.x
"""

import cv2
import numpy as np
import mediapipe as mp
from collections import deque
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from mediapipe.tasks.python.components.containers.landmark import NormalizedLandmark

# ── Landmark indices (from PoseLandmark enum) ────────────────────────────────
PoseLandmark = mp.tasks.vision.PoseLandmark
SHOULDER_IDX = int(PoseLandmark.RIGHT_SHOULDER)
ELBOW_IDX    = int(PoseLandmark.RIGHT_ELBOW)
WRIST_IDX    = int(PoseLandmark.RIGHT_WRIST)

# ── Posture thresholds (degrees) ─────────────────────────────────────────────
CORRECT_MIN = 80
CORRECT_MAX = 160

# ── Angle smoothing buffer ───────────────────────────────────────────────────
_angle_buffer: deque = deque(maxlen=5)

# ── Pose connections for drawing ─────────────────────────────────────────────
POSE_CONNECTIONS = mp.tasks.vision.PoseLandmarksConnections.POSE_LANDMARKS


def _build_landmarker(model_path: str) -> mp_vision.PoseLandmarker:
    """Create and return a PoseLandmarker instance for video (live) mode."""
    options = mp_vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=model_path),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.6,
        min_pose_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )
    return mp_vision.PoseLandmarker.create_from_options(options)


# Module-level landmarker (initialised on first import)
_MODEL_PATH = "pose_landmarker.task"
landmarker = _build_landmarker(_MODEL_PATH)
_frame_ts_ms: int = 0   # monotonic timestamp counter for VIDEO mode


# ── Core functions ────────────────────────────────────────────────────────────

def calculate_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """
    Angle at vertex b formed by vectors b→a and b→c.

    Args:
        a, b, c: [x, y] numpy arrays (shoulder, elbow, wrist).
    Returns:
        Angle in degrees (0–180).
    """
    ba = a - b
    bc = c - b
    cosine = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


def detect_pose(frame: np.ndarray):
    """
    Run PoseLandmarker on a BGR frame.

    Args:
        frame: BGR image from OpenCV.
    Returns:
        (frame, result) — original frame (unmodified) + PoseLandmarkerResult.
    """
    global _frame_ts_ms
    _frame_ts_ms += 33   # ~30 fps synthetic timestamp

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect_for_video(mp_image, _frame_ts_ms)
    return frame, result


def _draw_landmarks(frame: np.ndarray, landmarks: list) -> None:
    """Draw pose skeleton onto frame in-place."""
    h, w = frame.shape[:2]
    pts = {i: (int(lm.x * w), int(lm.y * h)) for i, lm in enumerate(landmarks)}

    for conn in POSE_CONNECTIONS:
        s, e = conn.start, conn.end
        if s in pts and e in pts:
            cv2.line(frame, pts[s], pts[e], (200, 200, 200), 1, cv2.LINE_AA)

    for pt in pts.values():
        cv2.circle(frame, pt, 3, (255, 255, 255), -1, cv2.LINE_AA)


def analyze_posture(result, frame: np.ndarray) -> dict:
    """
    Extract shoulder–elbow–wrist angle, draw skeleton, classify posture.

    Args:
        result: PoseLandmarkerResult from detect_pose().
        frame:  BGR frame to draw landmarks on (modified in-place).
    Returns:
        dict with keys: detected, angle, status, feedback, arm_points.
    """
    if not result.pose_landmarks:
        return {"detected": False, "angle": None, "status": None,
                "feedback": "No person detected", "arm_points": []}

    landmarks = result.pose_landmarks[0]
    _draw_landmarks(frame, landmarks)

    h, w = frame.shape[:2]

    def to_px(lm: NormalizedLandmark) -> np.ndarray:
        return np.array([lm.x * w, lm.y * h])

    try:
        shoulder = to_px(landmarks[SHOULDER_IDX])
        elbow    = to_px(landmarks[ELBOW_IDX])
        wrist    = to_px(landmarks[WRIST_IDX])
    except (IndexError, AttributeError):
        return {"detected": False, "angle": None, "status": None,
                "feedback": "Landmarks missing", "arm_points": []}

    raw_angle = calculate_angle(shoulder, elbow, wrist)
    _angle_buffer.append(raw_angle)
    angle = float(np.mean(_angle_buffer))

    if CORRECT_MIN <= angle <= CORRECT_MAX:
        status, feedback = "Correct", "Correct posture"
    elif angle < CORRECT_MIN:
        status, feedback = "Incorrect", "Raise your arm higher"
    else:
        status, feedback = "Incorrect", "Lower your arm slightly"

    arm_points = [tuple(shoulder.astype(int)),
                  tuple(elbow.astype(int)),
                  tuple(wrist.astype(int))]

    return {
        "detected":   True,
        "angle":      round(angle, 1),
        "status":     status,
        "feedback":   feedback,
        "arm_points": arm_points,
    }
