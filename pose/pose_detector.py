"""
pose/pose_detector.py
MediaPipe PoseLandmarker wrapper.
Handles model loading, per-frame inference, and skeleton drawing.
"""

import os
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

# ── Landmark indices ──────────────────────────────────────────────────────────
PoseLandmark     = mp.tasks.vision.PoseLandmark
POSE_CONNECTIONS = mp.tasks.vision.PoseLandmarksConnections.POSE_LANDMARKS

# Arm landmark indices used by all exercises (right side)
LANDMARK_IDX = {
    "right_shoulder": int(PoseLandmark.RIGHT_SHOULDER),
    "right_elbow":    int(PoseLandmark.RIGHT_ELBOW),
    "right_wrist":    int(PoseLandmark.RIGHT_WRIST),
    "left_shoulder":  int(PoseLandmark.LEFT_SHOULDER),
    "left_elbow":     int(PoseLandmark.LEFT_ELBOW),
    "left_wrist":     int(PoseLandmark.LEFT_WRIST),
    "right_hip":      int(PoseLandmark.RIGHT_HIP),
    "left_hip":       int(PoseLandmark.LEFT_HIP),
}

# Resolve model path relative to this file so it works from any cwd
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "pose_landmarker.task")


class PoseDetector:
    """Wraps MediaPipe PoseLandmarker for per-frame video inference."""

    def __init__(self, model_path: str = _MODEL_PATH):
        options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=os.path.abspath(model_path)
            ),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.6,
            min_pose_presence_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)
        self._ts_ms: int = 0   # synthetic monotonic timestamp for VIDEO mode

    def detect(self, frame: np.ndarray):
        """
        Run inference on a BGR frame.

        Returns:
            PoseLandmarkerResult (pose_landmarks list may be empty).
        """
        self._ts_ms += 33   # ~30 fps
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        return self._landmarker.detect_for_video(mp_img, self._ts_ms)

    @staticmethod
    def draw_skeleton(frame: np.ndarray, landmarks: list) -> None:
        """Draw full pose skeleton onto frame in-place (grey bones, white dots)."""
        h, w = frame.shape[:2]
        pts = {i: (int(lm.x * w), int(lm.y * h)) for i, lm in enumerate(landmarks)}

        for conn in POSE_CONNECTIONS:
            s, e = conn.start, conn.end
            if s in pts and e in pts:
                cv2.line(frame, pts[s], pts[e], (180, 180, 180), 1, cv2.LINE_AA)

        for pt in pts.values():
            cv2.circle(frame, pt, 3, (255, 255, 255), -1, cv2.LINE_AA)

    @staticmethod
    def get_landmark_px(landmarks: list, name: str, frame_shape: tuple):
        """
        Return pixel (x, y) numpy array for a named landmark.

        Args:
            landmarks:   pose_landmarks[0] list from MediaPipe result.
            name:        key from LANDMARK_IDX dict.
            frame_shape: (h, w, ...) of the frame.
        Returns:
            np.ndarray [x, y] or None if not found.
        """
        idx = LANDMARK_IDX.get(name)
        if idx is None or idx >= len(landmarks):
            return None
        h, w = frame_shape[:2]
        lm = landmarks[idx]
        return np.array([lm.x * w, lm.y * h])
