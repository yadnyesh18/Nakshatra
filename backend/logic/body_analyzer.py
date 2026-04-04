"""
logic/body_analyzer.py
Analyses body proportions from MediaPipe landmarks to produce a BodyProfile
that drives adaptive skeleton rendering and rehab threshold adjustment.

Added: compute_torso_lean() — per-frame lateral lean detection for posture validation.
"""

import numpy as np
from collections import deque
from dataclasses import dataclass, field
from mediapipe.tasks.python.vision import PoseLandmark

_LM = PoseLandmark
IDX = {
    "nose":           int(_LM.NOSE),
    "left_shoulder":  int(_LM.LEFT_SHOULDER),
    "right_shoulder": int(_LM.RIGHT_SHOULDER),
    "left_elbow":     int(_LM.LEFT_ELBOW),
    "right_elbow":    int(_LM.RIGHT_ELBOW),
    "left_wrist":     int(_LM.LEFT_WRIST),
    "right_wrist":    int(_LM.RIGHT_WRIST),
    "left_hip":       int(_LM.LEFT_HIP),
    "right_hip":      int(_LM.RIGHT_HIP),
    "left_knee":      int(_LM.LEFT_KNEE),
    "right_knee":     int(_LM.RIGHT_KNEE),
}

_CALIB_FRAMES = 30

# Lean angle above this (degrees from vertical) → compensation detected
_LEAN_THRESHOLD = 10.0


@dataclass
class BodyProfile:
    # Normalised measurements (relative to torso height)
    shoulder_width:     float = 0.0
    hip_width:          float = 0.0
    upper_arm_len:      float = 0.0
    forearm_len:        float = 0.0
    torso_height:       float = 0.0

    # Body type classification
    shoulder_type:      str   = "unknown"
    limb_type:          str   = "unknown"
    body_label:         str   = "Analysing..."

    # Adaptive rendering (scaled to apparent body size in frame)
    joint_radius:       int   = 5
    bone_thickness:     int   = 2
    active_thickness:   int   = 4

    # Threshold offsets (degrees added to exercise thresholds)
    angle_offset:       float = 0.0
    rom_offset:         float = 0.0
    observed_max_angle: float = 0.0

    # Calibration state
    calibrated:         bool  = False
    frames_seen:        int   = 0


class BodyAnalyzer:
    """
    Accumulates landmark measurements over _CALIB_FRAMES frames,
    then locks a stable BodyProfile used for rendering and threshold adaptation.
    """

    def __init__(self, calib_frames: int = _CALIB_FRAMES):
        self._calib_frames = calib_frames
        self._buf: dict[str, deque] = {
            k: deque(maxlen=calib_frames)
            for k in ("shoulder_w", "hip_w", "upper_arm", "forearm", "torso_h")
        }
        self.profile = BodyProfile()

    def update(self, landmarks: list, frame_shape: tuple) -> BodyProfile:
        h, w = frame_shape[:2]

        def px(name):
            idx = IDX.get(name)
            if idx is None or idx >= len(landmarks):
                return None
            lm = landmarks[idx]
            if hasattr(lm, "visibility") and lm.visibility < 0.5:
                return None
            return np.array([lm.x * w, lm.y * h])

        ls, rs = px("left_shoulder"),  px("right_shoulder")
        lh, rh = px("left_hip"),       px("right_hip")
        le, re = px("left_elbow"),     px("right_elbow")
        lw, rw = px("left_wrist"),     px("right_wrist")

        if any(p is None for p in [ls, rs, lh, rh]):
            return self.profile

        torso_h = float(np.linalg.norm((ls + rs) / 2 - (lh + rh) / 2))
        if torso_h < 10:
            return self.profile

        self._buf["torso_h"].append(torso_h)
        self._buf["shoulder_w"].append(np.linalg.norm(ls - rs) / torso_h)
        self._buf["hip_w"].append(np.linalg.norm(lh - rh) / torso_h)

        if le is not None and re is not None:
            upper = (np.linalg.norm(ls - le) + np.linalg.norm(rs - re)) / 2
        elif le is not None:
            upper = np.linalg.norm(ls - le)
        elif re is not None:
            upper = np.linalg.norm(rs - re)
        else:
            upper = None

        fore = None
        if lw is not None and le is not None:
            fore = np.linalg.norm(le - lw)
        elif rw is not None and re is not None:
            fore = np.linalg.norm(re - rw)

        if upper is not None: self._buf["upper_arm"].append(upper / torso_h)
        if fore   is not None: self._buf["forearm"].append(fore / torso_h)

        self.profile.frames_seen += 1

        if (not self.profile.calibrated
                and self.profile.frames_seen >= self._calib_frames
                and len(self._buf["shoulder_w"]) >= self._calib_frames):
            self._lock_profile()

        self._update_render_params(torso_h)
        return self.profile

    def reset(self) -> None:
        for buf in self._buf.values():
            buf.clear()
        self.profile = BodyProfile()

    # ── Torso lean (called per-frame from ExerciseClassifier) ─────────────────

    @staticmethod
    def compute_torso_lean(landmarks: list, frame_shape: tuple) -> dict:
        """
        Compute lateral torso lean angle from shoulder and hip midpoints.

        The torso vector runs from hip-midpoint → shoulder-midpoint.
        Lean is measured as the angle between this vector and vertical (0°=upright).

        Args:
            landmarks:   pose_landmarks[0] from MediaPipe result.
            frame_shape: (h, w, ...) of the current frame.
        Returns:
            dict with:
                lean_angle  (float) — degrees from vertical (0 = upright)
                is_leaning  (bool)  — True if lean > _LEAN_THRESHOLD
                direction   (str)   — "left" | "right" | "upright"
        """
        h, w = frame_shape[:2]

        def _px(idx_name: str):
            idx = IDX.get(idx_name)
            if idx is None or idx >= len(landmarks):
                return None
            lm = landmarks[idx]
            if hasattr(lm, "visibility") and lm.visibility < 0.4:
                return None
            return np.array([lm.x * w, lm.y * h])

        ls = _px("left_shoulder")
        rs = _px("right_shoulder")
        lh = _px("left_hip")
        rh = _px("right_hip")

        if any(p is None for p in [ls, rs, lh, rh]):
            return {"lean_angle": 0.0, "is_leaning": False, "direction": "upright"}

        shoulder_mid = (ls + rs) / 2
        hip_mid      = (lh + rh) / 2

        # Torso vector: hip → shoulder (pointing upward in image = negative y)
        torso_vec = shoulder_mid - hip_mid

        # Vertical reference in image coords: (0, -1) = straight up
        vertical  = np.array([0.0, -1.0])

        # Angle between torso vector and vertical
        denom     = np.linalg.norm(torso_vec) + 1e-6
        cosine    = np.dot(torso_vec / denom, vertical)
        lean_deg  = float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))

        # Direction: positive x-component of torso = leaning right in image
        # (mirrored feed: right in image = patient's left)
        direction = "upright"
        if lean_deg > _LEAN_THRESHOLD:
            direction = "right" if torso_vec[0] > 0 else "left"

        return {
            "lean_angle": round(lean_deg, 1),
            "is_leaning": lean_deg > _LEAN_THRESHOLD,
            "direction":  direction,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _lock_profile(self) -> None:
        p = self.profile
        p.shoulder_width = float(np.median(self._buf["shoulder_w"]))
        p.hip_width      = float(np.median(self._buf["hip_w"]))
        p.torso_height   = float(np.median(self._buf["torso_h"]))
        if self._buf["upper_arm"]: p.upper_arm_len = float(np.median(self._buf["upper_arm"]))
        if self._buf["forearm"]:   p.forearm_len   = float(np.median(self._buf["forearm"]))

        # Shoulder type
        if p.shoulder_width > 1.05:
            p.shoulder_type, shoulder_offset = "broad",   -8.0
        elif p.shoulder_width < 0.75:
            p.shoulder_type, shoulder_offset = "narrow",  +5.0
        else:
            p.shoulder_type, shoulder_offset = "average",  0.0

        # Limb type
        if p.upper_arm_len > 0.60:
            p.limb_type, limb_offset = "long",    -5.0
        elif 0 < p.upper_arm_len < 0.40:
            p.limb_type, limb_offset = "short",   +5.0
        else:
            p.limb_type, limb_offset = "average",  0.0

        p.angle_offset = shoulder_offset + limb_offset

        # ROM offset: detect pain-guarding (arm elevated at rest)
        p.rom_offset = p.observed_max_angle = 0.0
        if self._buf["upper_arm"]:
            resting_elev = float(np.median(self._buf["upper_arm"]))
            if resting_elev > 0.55:
                p.observed_max_angle = round((resting_elev - 0.45) * 100, 1)
                p.rom_offset         = -min(30.0, p.observed_max_angle)

        parts = []
        if p.shoulder_type != "average": parts.append(p.shoulder_type.capitalize() + " shoulders")
        if p.limb_type      != "average": parts.append(p.limb_type.capitalize() + " arms")
        if p.rom_offset < 0:             parts.append("Limited ROM detected")
        p.body_label  = ", ".join(parts) if parts else "Average build"
        p.calibrated  = True

    def _update_render_params(self, torso_h: float) -> None:
        scale = np.clip(torso_h / 250.0, 0.5, 2.0)
        p = self.profile
        p.joint_radius     = max(3, int(5 * scale))
        p.bone_thickness   = max(1, int(2 * scale))
        p.active_thickness = max(3, int(5 * scale))
        p.torso_height     = torso_h
