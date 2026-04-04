"""
logic/exercise_classifier.py
Rehab exercise registry and posture classifier for joint fracture recovery.
"""

from pose.pose_detector import PoseDetector, LANDMARK_IDX
from logic.angle import calculate_angle, AngleSmoother

EXERCISES: dict = {
    "pendulum_swing": {
        "display_name": "Pendulum Swing",
        "description":  "Gentle gravity-assisted shoulder movement. Let the arm hang and swing slowly.",
        "landmarks":    ["right_shoulder", "right_elbow", "right_wrist"],
        "invert":       True,
        "hold_sec":     0,
        "stages": [
            {"label": "Stage 1 — Minimal",  "correct_min": 5,  "correct_max": 20, "partial_range": [2,  5]},
            {"label": "Stage 2 — Moderate", "correct_min": 20, "correct_max": 40, "partial_range": [10, 20]},
            {"label": "Stage 3 — Full",     "correct_min": 40, "correct_max": 70, "partial_range": [25, 40]},
        ],
    },
    "arm_raise": {
        "display_name": "Assisted Arm Raise",
        "description":  "Slowly raise the arm forward. Use the other hand to assist if needed.",
        "landmarks":    ["right_shoulder", "right_elbow", "right_wrist"],
        "invert":       True,
        "hold_sec":     2,
        "stages": [
            {"label": "Stage 1 — Low",  "correct_min": 15, "correct_max": 40,  "partial_range": [5,  15]},
            {"label": "Stage 2 — Mid",  "correct_min": 40, "correct_max": 80,  "partial_range": [20, 40]},
            {"label": "Stage 3 — High", "correct_min": 80, "correct_max": 130, "partial_range": [50, 80]},
        ],
    },
    "shoulder_abduction": {
        "display_name": "Side Arm Lift",
        "description":  "Raise the arm out to the side. Keep elbow slightly bent. Stop at pain.",
        "landmarks":    ["right_hip", "right_shoulder", "right_elbow"],
        "invert":       True,
        "hold_sec":     2,
        "stages": [
            {"label": "Stage 1 — Low",  "correct_min": 10, "correct_max": 30,  "partial_range": [4,  10]},
            {"label": "Stage 2 — Mid",  "correct_min": 30, "correct_max": 70,  "partial_range": [15, 30]},
            {"label": "Stage 3 — Full", "correct_min": 70, "correct_max": 120, "partial_range": [45, 70]},
        ],
    },
    "shoulder_rotation": {
        "display_name": "Shoulder External Rotation",
        "description":  "Elbow at 90°, rotate forearm outward. Keep upper arm still.",
        "landmarks":    ["right_shoulder", "right_elbow", "right_wrist"],
        "invert":       False,
        "hold_sec":     3,
        "stages": [
            {"label": "Stage 1 — Minimal",  "correct_min": 150, "correct_max": 175, "partial_range": [140, 150]},
            {"label": "Stage 2 — Moderate", "correct_min": 130, "correct_max": 155, "partial_range": [120, 130]},
            {"label": "Stage 3 — Full",     "correct_min": 110, "correct_max": 140, "partial_range": [100, 110]},
        ],
    },
    "elbow_flexion": {
        "display_name": "Elbow Bend",
        "description":  "Slowly bend the elbow, bringing hand toward shoulder. Keep upper arm still.",
        "landmarks":    ["right_shoulder", "right_elbow", "right_wrist"],
        "invert":       False,
        "hold_sec":     2,
        "stages": [
            {"label": "Stage 1 — Minimal",  "correct_min": 140, "correct_max": 170, "partial_range": [155, 170]},
            {"label": "Stage 2 — Moderate", "correct_min": 100, "correct_max": 140, "partial_range": [120, 140]},
            {"label": "Stage 3 — Full",     "correct_min": 50,  "correct_max": 100, "partial_range": [80,  100]},
        ],
    },
    "elbow_extension": {
        "display_name": "Elbow Straighten",
        "description":  "Slowly straighten the elbow from a bent position. Do not force past comfort.",
        "landmarks":    ["right_shoulder", "right_elbow", "right_wrist"],
        "invert":       True,
        "hold_sec":     2,
        "stages": [
            {"label": "Stage 1 — Minimal",  "correct_min": 10, "correct_max": 30,  "partial_range": [4,  10]},
            {"label": "Stage 2 — Moderate", "correct_min": 30, "correct_max": 60,  "partial_range": [15, 30]},
            {"label": "Stage 3 — Full",     "correct_min": 60, "correct_max": 100, "partial_range": [40, 60]},
        ],
    },
}

_STRAIN_DROP_THRESHOLD = 20.0


class ExerciseClassifier:

    def __init__(self, exercise_name: str = "arm_raise", stage: int = 0):
        if exercise_name not in EXERCISES:
            raise ValueError(f"Unknown exercise '{exercise_name}'. Available: {list(EXERCISES.keys())}")
        self.exercise_name = exercise_name
        self.config        = EXERCISES[exercise_name]
        self.stage         = max(0, min(stage, len(self.config["stages"]) - 1))
        self._smoother     = AngleSmoother(window=7)
        self._prev_angle:  float | None = None
        self._strain_flag: bool         = False

    def switch_exercise(self, exercise_name: str, stage: int = 0) -> None:
        if exercise_name not in EXERCISES:
            raise ValueError(f"Unknown exercise '{exercise_name}'.")
        self.exercise_name = exercise_name
        self.config        = EXERCISES[exercise_name]
        self.stage         = max(0, min(stage, len(self.config["stages"]) - 1))
        self._smoother.reset()
        self._prev_angle  = None
        self._strain_flag = False

    def set_stage(self, stage: int) -> None:
        self.stage = max(0, min(stage, len(self.config["stages"]) - 1))
        self._smoother.reset()

    def classify(self, landmarks: list, frame_shape: tuple, body_profile=None) -> dict:
        cfg       = self.config
        stage_cfg = cfg["stages"][self.stage]

        points = [PoseDetector.get_landmark_px(landmarks, n, frame_shape) for n in cfg["landmarks"]]
        if any(p is None for p in points):
            return self._empty_result(cfg, stage_cfg)

        a, b, c   = points
        raw_angle = calculate_angle(a, b, c)
        if cfg.get("invert", False):
            raw_angle = 180.0 - raw_angle
        angle = self._smoother.update(raw_angle)

        self._strain_flag = (
            self._prev_angle is not None
            and (self._prev_angle - angle) > _STRAIN_DROP_THRESHOLD
        )
        self._prev_angle = angle

        offset = 0.0
        if body_profile is not None and body_profile.calibrated:
            offset = body_profile.angle_offset + getattr(body_profile, "rom_offset", 0.0)

        t_min = stage_cfg["correct_min"] + offset
        t_max = stage_cfg["correct_max"] + offset
        p_lo  = stage_cfg["partial_range"][0] + offset

        status, feedback = self._classify_angle(
            angle, t_min, t_max, p_lo, self._strain_flag
        )

        return {
            "detected":       True,
            "angle":          round(angle, 1),
            "status":         status,
            "feedback":       feedback,
            "arm_points":     [tuple(p.astype(int)) for p in points],
            "exercise_name":  self.exercise_name,
            "stage":          self.stage,
            "stage_label":    stage_cfg["label"],
            "active_indices": {LANDMARK_IDX[n] for n in cfg["landmarks"] if n in LANDMARK_IDX},
            "threshold_min":  round(t_min, 1),
            "threshold_max":  round(t_max, 1),
            "hold_sec":       cfg.get("hold_sec", 0),
            "strain_warning": self._strain_flag,
            "description":    cfg.get("description", ""),
        }

    def _empty_result(self, cfg: dict, stage_cfg: dict) -> dict:
        return {
            "detected": False, "angle": None, "status": None,
            "feedback": "Position yourself so your arm is visible",
            "arm_points": [], "exercise_name": self.exercise_name,
            "stage": self.stage, "stage_label": stage_cfg["label"],
            "active_indices": set(),
            "threshold_min": stage_cfg["correct_min"],
            "threshold_max": stage_cfg["correct_max"],
            "hold_sec": cfg.get("hold_sec", 0),
            "strain_warning": False, "description": cfg.get("description", ""),
        }

    @staticmethod
    def _classify_angle(angle: float, t_min: float, t_max: float,
                        p_lo: float, strain: bool) -> tuple[str, str]:
        if strain:
            return "Warning", "Stop — sudden movement detected. Rest and breathe."
        if t_min <= angle <= t_max:
            return "Correct", "Good — hold this position steadily."
        if p_lo <= angle < t_min:
            return "Partial", "Almost there — gently move a little further."
        if angle < p_lo:
            return "Rest",    "Slowly begin the movement when ready."
        return "Correct", "Great range — slowly return to start."
