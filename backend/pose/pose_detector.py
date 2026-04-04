"""
pose/pose_detector.py
MediaPipe PoseLandmarker wrapper with body-adaptive skeleton rendering.
"""

import os
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

PoseLandmark     = mp.tasks.vision.PoseLandmark
POSE_CONNECTIONS = mp.tasks.vision.PoseLandmarksConnections.POSE_LANDMARKS

LANDMARK_IDX = {
    "right_shoulder": int(PoseLandmark.RIGHT_SHOULDER),
    "right_elbow":    int(PoseLandmark.RIGHT_ELBOW),
    "right_wrist":    int(PoseLandmark.RIGHT_WRIST),
    "left_shoulder":  int(PoseLandmark.LEFT_SHOULDER),
    "left_elbow":     int(PoseLandmark.LEFT_ELBOW),
    "left_wrist":     int(PoseLandmark.LEFT_WRIST),
    "right_hip":      int(PoseLandmark.RIGHT_HIP),
    "left_hip":       int(PoseLandmark.LEFT_HIP),
    "right_knee":     int(PoseLandmark.RIGHT_KNEE),
    "left_knee":      int(PoseLandmark.LEFT_KNEE),
    "nose":           int(PoseLandmark.NOSE),
}

# Colour per body region (BGR)
_REGION_COLOR = {
    "face":      (180, 180, 180),
    "torso":     (100, 200, 255),
    "right_arm": (0,   200, 100),
    "left_arm":  (0,   140, 255),
    "right_leg": (200, 100, 255),
    "left_leg":  (255, 180,  60),
}

# Landmark index → region
_LM_REGION: dict[int, str] = {
    0: "face",  1: "face",  2: "face",  3: "face",  4: "face",
    5: "face",  6: "face",  7: "face",  8: "face",  9: "face", 10: "face",
    11: "left_arm",  12: "right_arm",
    13: "left_arm",  14: "right_arm",
    15: "left_arm",  16: "right_arm",
    17: "left_arm",  18: "right_arm",
    19: "left_arm",  20: "right_arm",
    21: "left_arm",  22: "right_arm",
    23: "left_leg",  24: "right_leg",
    25: "left_leg",  26: "right_leg",
    27: "left_leg",  28: "right_leg",
    29: "left_leg",  30: "right_leg",
    31: "left_leg",  32: "right_leg",
}

_MODEL_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "models", "pose_landmarker.task"))


class PoseDetector:
    """Wraps MediaPipe PoseLandmarker for per-frame video inference."""

    def __init__(self, model_path: str = _MODEL_PATH):
        options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=os.path.abspath(model_path)),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.6,
            min_pose_presence_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)
        self._ts_ms: int = 0

    def detect(self, frame: np.ndarray):
        """Run inference on a BGR frame. Returns PoseLandmarkerResult."""
        self._ts_ms += 33
        rgb    = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        return self._landmarker.detect_for_video(mp_img, self._ts_ms)

    @staticmethod
    def draw_skeleton(frame: np.ndarray, landmarks: list,
                      profile=None, active_indices: set | None = None) -> None:
        """Draw body-adaptive skeleton. Active joints are highlighted."""
        h, w = frame.shape[:2]

        joint_r    = profile.joint_radius     if profile else 5
        bone_thick = profile.bone_thickness   if profile else 2
        act_thick  = profile.active_thickness if profile else 4
        active_indices = active_indices or set()

        # Build pixel map, skip low-visibility landmarks
        pts: dict[int, tuple] = {
            i: (int(lm.x * w), int(lm.y * h))
            for i, lm in enumerate(landmarks)
            if getattr(lm, "visibility", 1.0) >= 0.35
        }

        # Bones
        for conn in POSE_CONNECTIONS:
            s, e = conn.start, conn.end
            if s not in pts or e not in pts:
                continue
            if s in active_indices or e in active_indices:
                cv2.line(frame, pts[s], pts[e], (255, 255, 255), act_thick, cv2.LINE_AA)
            else:
                region = _LM_REGION.get(s) or _LM_REGION.get(e) or "torso"
                cv2.line(frame, pts[s], pts[e],
                         _REGION_COLOR.get(region, (160, 160, 160)), bone_thick, cv2.LINE_AA)

        # Joints
        for i, pt in pts.items():
            if i in active_indices:
                cv2.circle(frame, pt, joint_r + 3, (255, 200, 0),   2,  cv2.LINE_AA)
                cv2.circle(frame, pt, joint_r,     (255, 255, 255), -1, cv2.LINE_AA)
            else:
                color = _REGION_COLOR.get(_LM_REGION.get(i, "torso"), (200, 200, 200))
                cv2.circle(frame, pt, joint_r,     color,        -1, cv2.LINE_AA)
                cv2.circle(frame, pt, joint_r + 1, (30, 30, 30),  1, cv2.LINE_AA)

        # Calibration progress bar
        if profile is not None and not profile.calibrated:
            progress = min(profile.frames_seen / 30, 1.0)
            bar_w    = int(w * 0.4)
            bar_x    = w // 2 - bar_w // 2
            cv2.rectangle(frame, (bar_x, 20), (bar_x + bar_w, 32), (40, 40, 40), -1)
            cv2.rectangle(frame, (bar_x, 20), (bar_x + int(bar_w * progress), 32), (0, 200, 100), -1)
            cv2.putText(frame, f"Calibrating body shape... {int(progress * 100)}%",
                        (bar_x, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
        elif profile is not None and profile.calibrated:
            cv2.putText(frame, profile.body_label, (w // 2 - 120, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 220, 255), 1, cv2.LINE_AA)

    @staticmethod
    def get_landmark_px(landmarks: list, name: str, frame_shape: tuple):
        """Return pixel [x, y] for a named landmark, or None if missing/occluded."""
        idx = LANDMARK_IDX.get(name)
        if idx is None or idx >= len(landmarks):
            return None
        lm = landmarks[idx]
        if hasattr(lm, "visibility") and lm.visibility < 0.35:
            return None
        h, w = frame_shape[:2]
        return np.array([lm.x * w, lm.y * h])
