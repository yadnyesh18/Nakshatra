"""
logic/exercise_classifier.py
Config-driven exercise registry and posture classifier.

Adding a new exercise requires only a new entry in EXERCISES — no core logic changes.
"""

from pose.pose_detector import PoseDetector
from logic.angle import calculate_angle, AngleSmoother

# ── Exercise configuration registry ──────────────────────────────────────────
# Each entry defines:
#   landmarks   : three named landmarks (from LANDMARK_IDX) forming the angle
#   correct_min : lower bound of correct range (degrees)
#   correct_max : upper bound of correct range (degrees)
#   partial_range: [low, high] — "almost there" zone below correct_min
#   display_name: human-readable label shown on screen
EXERCISES: dict = {
    "arm_raise": {
        "landmarks":    ["right_shoulder", "right_elbow", "right_wrist"],
        "correct_min":  80,
        "correct_max":  160,
        "partial_range": [40, 80],
        "display_name": "Arm Raise",
    },
    "shoulder_abduction": {
        "landmarks":    ["right_hip", "right_shoulder", "right_elbow"],
        "correct_min":  70,
        "correct_max":  150,
        "partial_range": [30, 70],
        "display_name": "Shoulder Abduction",
    },
    "elbow_flexion": {
        "landmarks":    ["right_shoulder", "right_elbow", "right_wrist"],
        "correct_min":  40,
        "correct_max":  90,
        "partial_range": [20, 40],
        "display_name": "Elbow Flexion",
    },
}


class ExerciseClassifier:
    """
    Classifies posture for a chosen exercise using landmark angles.

    Usage:
        clf = ExerciseClassifier("arm_raise")
        result = clf.classify(landmarks, frame_shape)
    """

    def __init__(self, exercise_name: str = "arm_raise"):
        if exercise_name not in EXERCISES:
            raise ValueError(
                f"Unknown exercise '{exercise_name}'. "
                f"Available: {list(EXERCISES.keys())}"
            )
        self.exercise_name = exercise_name
        self.config = EXERCISES[exercise_name]
        self._smoother = AngleSmoother(window=7)

    def switch_exercise(self, exercise_name: str) -> None:
        """Hot-swap to a different exercise and reset smoother."""
        if exercise_name not in EXERCISES:
            raise ValueError(f"Unknown exercise '{exercise_name}'.")
        self.exercise_name = exercise_name
        self.config = EXERCISES[exercise_name]
        self._smoother.reset()

    def classify(self, landmarks: list, frame_shape: tuple) -> dict:
        """
        Compute smoothed angle and classify posture for the active exercise.

        Args:
            landmarks:   pose_landmarks[0] from MediaPipe result.
            frame_shape: (h, w, ...) of the current frame.
        Returns:
            dict — angle, status, feedback, arm_points, exercise_name.
            Returns detected=False dict on missing landmarks.
        """
        cfg = self.config
        lm_names = cfg["landmarks"]

        points = [
            PoseDetector.get_landmark_px(landmarks, name, frame_shape)
            for name in lm_names
        ]

        if any(p is None for p in points):
            return {"detected": False, "angle": None, "status": None,
                    "feedback": "Landmarks missing", "arm_points": [],
                    "exercise_name": self.exercise_name}

        a, b, c = points
        raw_angle = calculate_angle(a, b, c)
        angle = self._smoother.update(raw_angle)

        status, feedback = self._classify_angle(angle, cfg)

        return {
            "detected":      True,
            "angle":         round(angle, 1),
            "status":        status,
            "feedback":      feedback,
            "arm_points":    [tuple(p.astype(int)) for p in points],
            "exercise_name": self.exercise_name,
        }

    @staticmethod
    def _classify_angle(angle: float, cfg: dict) -> tuple:
        """Map angle to (status, feedback) using exercise config."""
        lo, hi = cfg["correct_min"], cfg["correct_max"]
        p_lo, p_hi = cfg["partial_range"]

        if lo <= angle <= hi:
            return "Correct", "Good posture — keep it up!"
        elif p_lo <= angle < lo:
            return "Partial", "Almost there — lift a bit higher"
        elif angle < p_lo:
            return "Incorrect", "Lift your arm higher"
        else:
            return "Incorrect", "Lower your arm slightly"
