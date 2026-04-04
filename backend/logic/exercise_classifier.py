"""
logic/exercise_classifier.py
Rehab exercise registry and multi-factor posture classifier.

Evaluation factors (beyond single-angle ROM):
  1. ROM score      (0–40) — how well angle hits the target range
  2. Stability score(0–30) — low variance = steady hold
  3. Smoothness score(0–30)— low angular velocity = controlled movement
  4. Torso lean check      — penalises compensatory body lean
  Total form_score 0–100 → Excellent / Good / Needs Improvement
"""

from pose.pose_detector import PoseDetector, LANDMARK_IDX
from logic.angle import calculate_angle, AngleSmoother, AngleMetrics, LiveMetricsPrinter
from logic.body_analyzer import BodyAnalyzer

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
        "description":  "Start with arm straight. Slowly bend the elbow, bringing hand toward shoulder. Keep upper arm still.",
        "landmarks":    ["right_shoulder", "right_elbow", "right_wrist"],
        "invert":       False,   # raw angle: straight=180°, fully bent=~30°
        "direction":    "flex",  # movement goes from high angle → low angle
        "hold_sec":     2,
        "stages": [
            # S1: slight bend — patient starts straight (~180°) and bends to 130–160°
            {"label": "Stage 1 — Slight Bend",  "correct_min": 130, "correct_max": 160, "partial_range": [160, 180]},
            # S2: moderate bend — elbow reaches 90–130°
            {"label": "Stage 2 — Moderate Bend", "correct_min": 90,  "correct_max": 130, "partial_range": [130, 160]},
            # S3: full bend — elbow reaches 40–90° (hand near shoulder)
            {"label": "Stage 3 — Full Bend",     "correct_min": 40,  "correct_max": 90,  "partial_range": [90,  130]},
        ],
    },
    "elbow_extension": {
        "display_name": "Elbow Straighten",
        "description":  "Start with elbow bent. Slowly straighten the elbow. Do not force past comfort.",
        "landmarks":    ["right_shoulder", "right_elbow", "right_wrist"],
        "invert":       False,   # raw angle: bent=~40°, straight=~170° — NO invert needed
        "direction":    "extend",# movement goes from low angle → high angle
        "hold_sec":     2,
        "stages": [
            # S1: slight straightening — patient starts bent and reaches 60–90°
            {"label": "Stage 1 — Slight Straighten",  "correct_min": 60,  "correct_max": 90,  "partial_range": [40,  60]},
            # S2: moderate straightening — elbow reaches 90–130°
            {"label": "Stage 2 — Moderate Straighten", "correct_min": 90,  "correct_max": 130, "partial_range": [60,  90]},
            # S3: full straightening — elbow reaches 130–170°
            {"label": "Stage 3 — Full Straighten",     "correct_min": 130, "correct_max": 170, "partial_range": [100, 130]},
        ],
    },
}

_STRAIN_DROP_THRESHOLD = 20.0


# ── Exercise Auto-Configurator ───────────────────────────────────────────────────────────────

class ExerciseAutoConfigurator:
    """
    Parses a plain-English exercise description and auto-configures:
      - joint landmark triplet
      - movement direction (flex / extend)
      - invert flag
      - 3 progressive stage thresholds (calibrated from live frames)

    Two phases:
      Phase 1 (frames 1-15)  : patient holds REST position → records rest_angle
      Phase 2 (frames 16-45) : patient moves to MAX range  → records max_angle
      After frame 45         : stages locked, calibration complete

    Usage:
        cfg = ExerciseAutoConfigurator("raise your arm forward")
        # each frame before calibration is complete:
        cfg.feed(raw_angle)          → returns False (still calibrating)
        # once complete:
        cfg.config                   → dict shaped like an EXERCISES entry
        cfg.calibrated               → True
    """

    # ── Keyword maps ───────────────────────────────────────────────────────────────

    # Body region → default right-side landmark triplet
    _JOINT_MAP = {
        "arm":      ["right_shoulder", "right_elbow", "right_wrist"],
        "shoulder": ["right_shoulder", "right_elbow", "right_wrist"],
        "elbow":    ["right_shoulder", "right_elbow", "right_wrist"],
        "wrist":    ["right_shoulder", "right_elbow", "right_wrist"],
        "leg":      ["right_hip",      "right_knee",  "right_ankle"],
        "knee":     ["right_hip",      "right_knee",  "right_ankle"],
        "hip":      ["right_hip",      "right_knee",  "right_ankle"],
        "abduct":   ["right_hip",      "right_shoulder", "right_elbow"],
        "side":     ["right_hip",      "right_shoulder", "right_elbow"],
    }

    # Left-side override
    _LEFT_OVERRIDE = {
        "right_shoulder": "left_shoulder",
        "right_elbow":    "left_elbow",
        "right_wrist":    "left_wrist",
        "right_hip":      "left_hip",
        "right_knee":     "left_knee",
    }

    # Movement direction keywords
    _FLEX_WORDS    = {"bend", "flex", "curl", "lower", "close", "bring", "contract"}
    _EXTEND_WORDS  = {"raise", "lift", "extend", "straighten", "open",
                      "stretch", "elevate", "abduct", "rotate", "turn"}

    # Calibration frame counts
    _REST_FRAMES   = 15   # frames to measure rest angle
    _MOVE_FRAMES   = 30   # frames to measure max angle
    _TOTAL_FRAMES  = _REST_FRAMES + _MOVE_FRAMES

    def __init__(self, description: str):
        self.description  = description
        self.calibrated   = False
        self.config: dict = {}

        self._frame_count = 0
        self._rest_buf:  list[float] = []
        self._move_buf:  list[float] = []

        # Parse description immediately
        words = set(description.lower().replace(",", " ").replace(".", " ").split())
        self._landmarks  = self._infer_landmarks(words)
        self._direction  = self._infer_direction(words)
        self._side       = "left" if "left" in words else "right"

        if self._side == "left":
            self._landmarks = [
                self._LEFT_OVERRIDE.get(lm, lm) for lm in self._landmarks
            ]

        # Print what was inferred
        print(f"\n\033[94m[AUTO-CONFIG] Description : {description}\033[0m")
        print(f"\033[94m[AUTO-CONFIG] Joints      : {' → '.join(self._landmarks)}\033[0m")
        print(f"\033[94m[AUTO-CONFIG] Direction   : {self._direction}\033[0m")
        print(f"\033[94m[AUTO-CONFIG] Calibrating : hold REST position for {self._REST_FRAMES} frames,"
              f" then move to MAX range for {self._MOVE_FRAMES} frames...\033[0m\n")

    # ── Public API ───────────────────────────────────────────────────────────────────

    @property
    def landmarks(self) -> list:
        return self._landmarks

    def feed(self, raw_angle: float) -> bool:
        """
        Feed one frame's raw angle during calibration.

        Returns True when calibration is complete.
        """
        if self.calibrated:
            return True

        self._frame_count += 1

        if self._frame_count <= self._REST_FRAMES:
            # Phase 1: record rest position
            self._rest_buf.append(raw_angle)
            pct = int(self._frame_count / self._REST_FRAMES * 100)
            print(f"  \033[93m[CALIB] Phase 1 — REST  {pct:3d}%  angle={raw_angle:.1f}°\033[0m",
                  end="\r", flush=True)

        else:
            # Phase 2: patient moves to max range
            self._move_buf.append(raw_angle)
            pct = int((self._frame_count - self._REST_FRAMES) / self._MOVE_FRAMES * 100)
            cur_max = max(self._move_buf) if self._direction == "extend" else min(self._move_buf)
            print(f"  \033[92m[CALIB] Phase 2 — MOVE  {pct:3d}%  "
                  f"angle={raw_angle:.1f}°  peak={cur_max:.1f}°\033[0m",
                  end="\r", flush=True)

        if self._frame_count >= self._TOTAL_FRAMES:
            self._lock_config()
            return True

        return False

    # ── Internal ─────────────────────────────────────────────────────────────────────

    def _infer_landmarks(self, words: set) -> list:
        """Return landmark triplet based on body-region keywords."""
        # arm/shoulder/elbow/wrist keywords take priority over side/abduct
        for key in ("knee", "leg", "hip", "elbow", "wrist", "shoulder", "arm", "abduct", "side"):
            if key in words:
                return list(self._JOINT_MAP[key])
        return list(self._JOINT_MAP["arm"])

    def _infer_direction(self, words: set) -> str:
        """Return 'flex' or 'extend' based on movement keywords."""
        flex_hits    = len(words & self._FLEX_WORDS)
        extend_hits  = len(words & self._EXTEND_WORDS)
        return "flex" if flex_hits > extend_hits else "extend"

    def _lock_config(self) -> None:
        """Compute thresholds from calibration data and build config dict."""
        import numpy as np

        rest_angle = float(np.median(self._rest_buf))

        if self._direction == "extend":
            # Angle increases: rest is low, max is high
            max_angle = float(np.percentile(self._move_buf, 90))  # 90th pct avoids outliers
            invert    = False
            rom       = max_angle - rest_angle
            # Guard: if patient barely moved, set a minimum ROM
            rom       = max(rom, 20.0)
            s1_min = round(rest_angle + rom * 0.10)
            s1_max = round(rest_angle + rom * 0.35)
            s2_min = round(rest_angle + rom * 0.35)
            s2_max = round(rest_angle + rom * 0.65)
            s3_min = round(rest_angle + rom * 0.65)
            s3_max = round(rest_angle + rom * 0.95)
            p_lo1  = round(rest_angle)
            p_lo2  = round(s1_max)
            p_lo3  = round(s2_max)
            stages = [
                {"label": "Stage 1 — Low",  "correct_min": s1_min, "correct_max": s1_max,
                 "partial_range": [p_lo1, s1_min]},
                {"label": "Stage 2 — Mid",  "correct_min": s2_min, "correct_max": s2_max,
                 "partial_range": [p_lo2, s2_min]},
                {"label": "Stage 3 — Full", "correct_min": s3_min, "correct_max": s3_max,
                 "partial_range": [p_lo3, s3_min]},
            ]
        else:
            # Angle decreases: rest is high, max (target) is low
            max_angle = float(np.percentile(self._move_buf, 10))  # 10th pct = deepest bend
            invert    = False
            rom       = rest_angle - max_angle
            rom       = max(rom, 20.0)
            s1_max = round(rest_angle - rom * 0.10)
            s1_min = round(rest_angle - rom * 0.35)
            s2_max = round(rest_angle - rom * 0.35)
            s2_min = round(rest_angle - rom * 0.65)
            s3_max = round(rest_angle - rom * 0.65)
            s3_min = round(rest_angle - rom * 0.95)
            stages = [
                {"label": "Stage 1 — Slight",   "correct_min": s1_min, "correct_max": s1_max,
                 "partial_range": [s1_max, round(rest_angle)]},
                {"label": "Stage 2 — Moderate", "correct_min": s2_min, "correct_max": s2_max,
                 "partial_range": [s2_max, s1_max]},
                {"label": "Stage 3 — Full",     "correct_min": s3_min, "correct_max": s3_max,
                 "partial_range": [s3_max, s2_max]},
            ]

        self.config = {
            "display_name": f"Auto: {self.description[:40]}",
            "description":  self.description,
            "landmarks":    self._landmarks,
            "invert":       invert,
            "direction":    self._direction,
            "hold_sec":     2,
            "stages":       stages,
        }
        self.calibrated = True

        # Print final config
        print(f"\n\n\033[92m[AUTO-CONFIG] Calibration complete!\033[0m")
        print(f"  Rest angle : {rest_angle:.1f}°")
        print(f"  Max angle  : {max_angle:.1f}°")
        print(f"  ROM        : {abs(max_angle - rest_angle):.1f}°")
        print(f"  Direction  : {self._direction}")
        for s in stages:
            print(f"  {s['label']:<22}: {s['correct_min']}° – {s['correct_max']}°")
        print()


# ── Form quality scorer ───────────────────────────────────────────────────────

class FormScorer:
    """
    Computes a 0–100 form quality score from three independent factors:

        ROM score       (0–40): how well the angle hits the target range
        Stability score (0–30): low angle variance = steady hold
        Smoothness score(0–30): low angular velocity = controlled movement

    A torso lean penalty (up to –15 pts) is applied when compensation is detected.

    Grade:
        85–100 → Excellent
        60–84  → Good
        < 60   → Needs Improvement
    """

    # Variance ceiling: above this → 0 stability points
    _MAX_VARIANCE  = 25.0   # deg²
    # Velocity ceiling: above this → 0 smoothness points
    _MAX_VELOCITY  = 15.0   # deg/frame
    # Lean penalty per degree above threshold
    _LEAN_PENALTY_PER_DEG = 1.0
    _MAX_LEAN_PENALTY     = 15.0

    @staticmethod
    def compute(angle: float, t_min: float, t_max: float,
                metrics: dict, lean: dict) -> dict:
        """
        Compute form score for one frame.

        Args:
            angle:   smoothed joint angle (degrees)
            t_min:   lower bound of correct range
            t_max:   upper bound of correct range
            metrics: output of AngleMetrics.update()
            lean:    output of BodyAnalyzer.compute_torso_lean()
        Returns:
            dict with: rom, stability, smoothness, lean_penalty,
                       total, grade, breakdown
        """
        # ── ROM score (0–40) ──────────────────────────────────────────────────
        # Full 40 pts when inside correct range.
        # Partial credit proportional to how close the angle is to the range.
        range_width = max(t_max - t_min, 1.0)
        if t_min <= angle <= t_max:
            rom = 40.0
        elif angle < t_min:
            # Distance below lower bound, normalised to range width
            deficit = t_min - angle
            rom = max(0.0, 40.0 * (1.0 - deficit / range_width))
        else:
            # Above upper bound — still good ROM, slight penalty for over-extension
            excess = angle - t_max
            rom = max(0.0, 40.0 * (1.0 - excess / range_width))

        # ── Stability score (0–30) ────────────────────────────────────────────
        # Linear decay from 30 (variance=0) to 0 (variance≥MAX_VARIANCE)
        variance   = metrics.get("variance", 0.0)
        stability  = max(0.0, 30.0 * (1.0 - variance / FormScorer._MAX_VARIANCE))

        # ── Smoothness score (0–30) ───────────────────────────────────────────
        # Linear decay from 30 (velocity=0) to 0 (velocity≥MAX_VELOCITY)
        velocity   = metrics.get("velocity", 0.0)
        smoothness = max(0.0, 30.0 * (1.0 - velocity / FormScorer._MAX_VELOCITY))

        # ── Torso lean penalty (0–15) ─────────────────────────────────────────
        lean_angle   = lean.get("lean_angle", 0.0)
        lean_penalty = min(
            FormScorer._MAX_LEAN_PENALTY,
            max(0.0, lean_angle * FormScorer._LEAN_PENALTY_PER_DEG)
        ) if lean.get("is_leaning") else 0.0

        total = max(0, min(100, round(rom + stability + smoothness - lean_penalty)))

        if total >= 85:
            grade = "Excellent"
        elif total >= 60:
            grade = "Good"
        else:
            grade = "Needs Improvement"

        return {
            "total":       total,
            "grade":       grade,
            "breakdown": {
                "rom":         round(rom, 1),
                "stability":   round(stability, 1),
                "smoothness":  round(smoothness, 1),
                "lean_penalty": round(lean_penalty, 1),
            },
        }


# ── Feedback engine ───────────────────────────────────────────────────────────

def _build_feedback(angle: float, t_min: float, t_max: float, p_lo: float,
                    strain: bool, metrics: dict, lean: dict,
                    form_score: dict, direction: str = "extend") -> tuple[str, str]:
    """
    Priority-ordered feedback engine.

    direction: "flex"   — correct movement decreases angle (elbow bend)
               "extend" — correct movement increases angle (elbow straighten,
                           arm raise, etc.)
    """
    # 1. Strain — always highest priority
    if strain:
        return "Warning", "Stop — sudden movement detected. Rest and breathe."

    # 2. Torso lean
    if lean.get("is_leaning"):
        side = "left" if lean.get("direction") == "left" else "right"
        return "Warning", f"Keep your body straight — you are leaning {side}."

    # 3. Jerky movement
    if not metrics.get("is_smooth", True):
        return "Incorrect", "Move slower — control the movement."

    # 4. Unstable hold
    if t_min <= angle <= t_max and not metrics.get("is_stable", True):
        return "Partial", "Keep your arm steady — reduce the shaking."

    # 5. ROM-based feedback — direction-aware
    if t_min <= angle <= t_max:
        grade = form_score.get("grade", "Good")
        if grade == "Excellent":
            return "Correct", "Excellent form — hold this position."
        return "Correct", "Good — hold this position steadily."

    if direction == "flex":
        # Angle decreases toward target (elbow bend: straight → bent)
        # Rest position = arm straight = high angle (above t_max)
        # partial_range for flex = [p_lo, p_hi] where p_hi > t_max
        # We use p_hi (partial_range[1]) as the upper partial boundary
        if angle > t_max:
            # Above correct zone — still bending toward target
            return "Partial", "Keep bending your elbow — almost in range."
        if angle < t_min:
            # Below correct zone — over-bent or at rest after completing
            return "Rest", "Good — slowly return to start position."
        # Should not reach here (covered by t_min <= angle <= t_max above)
        return "Partial", "Keep bending your elbow."
    else:
        # Angle increases toward target (elbow extend, arm raise, etc.)
        # angle < p_lo means not started yet
        # angle > t_max means over-extended
        if angle < p_lo:
            return "Rest",    "Slowly begin the movement when ready."
        if p_lo <= angle < t_min:
            return "Partial", "Almost there — gently move a little further."
        return "Correct",    "Great range — slowly return to start."


# ── Classifier ────────────────────────────────────────────────────────────────

class ExerciseClassifier:

    def __init__(self, exercise_name: str = "arm_raise", stage: int = 0):
        if exercise_name not in EXERCISES:
            raise ValueError(f"Unknown exercise '{exercise_name}'. Available: {list(EXERCISES.keys())}")
        self.exercise_name = exercise_name
        self.config        = EXERCISES[exercise_name]
        self.stage         = max(0, min(stage, len(self.config["stages"]) - 1))
        self._smoother     = AngleSmoother(window=7)
        self._metrics      = AngleMetrics(window=10)
        self._prev_angle:  float | None = None
        self._strain_flag: bool         = False
        self._auto:        ExerciseAutoConfigurator | None = None  # set by from_description()

    @classmethod
    def from_description(cls, description: str, stage: int = 0) -> "ExerciseClassifier":
        """
        Create a self-configuring classifier from a plain-English description.

        The first 45 frames of classify() are used for calibration:
          - Frames  1-15: patient holds REST position
          - Frames 16-45: patient moves to MAX comfortable range
        After frame 45, thresholds are locked and normal classification begins.

        Example:
            clf = ExerciseClassifier.from_description("raise your arm forward")
        """
        # Bootstrap with any valid exercise — config will be replaced after calibration
        obj = cls.__new__(cls)
        obj.exercise_name = "_auto"
        obj.config        = EXERCISES["arm_raise"]   # temporary placeholder
        obj.stage         = stage
        obj._smoother     = AngleSmoother(window=7)
        obj._metrics      = AngleMetrics(window=10)
        obj._prev_angle   = None
        obj._strain_flag  = False
        obj._auto         = ExerciseAutoConfigurator(description)
        return obj

    def switch_exercise(self, exercise_name: str, stage: int = 0) -> None:
        if exercise_name not in EXERCISES:
            raise ValueError(f"Unknown exercise '{exercise_name}'.")
        self.exercise_name = exercise_name
        self.config        = EXERCISES[exercise_name]
        self.stage         = max(0, min(stage, len(self.config["stages"]) - 1))
        self._smoother.reset()
        self._metrics.reset()
        self._prev_angle  = None
        self._strain_flag = False

    def set_stage(self, stage: int) -> None:
        self.stage = max(0, min(stage, len(self.config["stages"]) - 1))
        self._smoother.reset()
        self._metrics.reset()

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

        # ── Auto-calibration phase ─────────────────────────────────────────────────────────
        if self._auto is not None and not self._auto.calibrated:
            done = self._auto.feed(raw_angle)
            if done:
                # Calibration just completed — swap in the auto-generated config
                self.config        = self._auto.config
                self.stage         = max(0, min(self.stage, len(self.config["stages"]) - 1))
                self.exercise_name = "_auto"
            # Return a holding result during calibration so the pipeline keeps running
            phase = "REST" if self._auto._frame_count <= self._auto._REST_FRAMES else "MOVE"
            return {
                "detected": True, "angle": round(raw_angle, 1), "status": "Rest",
                "feedback": f"Calibrating... {phase} phase ({self._auto._frame_count}/{self._auto._TOTAL_FRAMES})",
                "arm_points": [tuple(p.astype(int)) for p in points],
                "exercise_name": "_auto", "stage": self.stage,
                "stage_label": "Calibrating",
                "active_indices": {LANDMARK_IDX[n] for n in self._auto.landmarks if n in LANDMARK_IDX},
                "threshold_min": 0, "threshold_max": 180,
                "hold_sec": 0, "strain_warning": False, "description": self._auto.description,
                "form_score":    {"total": 0, "grade": "Calibrating", "breakdown": {}},
                "angle_metrics": {"variance": 0.0, "velocity": 0.0, "is_stable": True, "is_smooth": True},
                "torso_lean":    {"lean_angle": 0.0, "is_leaning": False, "direction": "upright"},
            }
        angle = self._smoother.update(raw_angle)

        # ── Strain detection (existing) ───────────────────────────────────────
        self._strain_flag = (
            self._prev_angle is not None
            and (self._prev_angle - angle) > _STRAIN_DROP_THRESHOLD
        )
        self._prev_angle = angle

        # ── Movement quality metrics (NEW) ────────────────────────────────────
        angle_metrics = self._metrics.update(angle)

        # ── Torso lean check (NEW) ────────────────────────────────────────────
        lean = BodyAnalyzer.compute_torso_lean(landmarks, frame_shape)

        # ── Adaptive thresholds (existing) ───────────────────────────────────
        offset = 0.0
        if body_profile is not None and body_profile.calibrated:
            offset = body_profile.angle_offset + getattr(body_profile, "rom_offset", 0.0)

        t_min = stage_cfg["correct_min"] + offset
        t_max = stage_cfg["correct_max"] + offset
        p_lo  = stage_cfg["partial_range"][0] + offset

        # ── Form score (NEW) ──────────────────────────────────────────────────
        form_score = FormScorer.compute(angle, t_min, t_max, angle_metrics, lean)

        # ── Multi-factor feedback (NEW, replaces single _classify_angle call) ─
        status, feedback = _build_feedback(
            angle, t_min, t_max, p_lo,
            self._strain_flag, angle_metrics, lean, form_score,
            direction=cfg.get("direction", "extend"),
        )

        # ── Live terminal metrics output ──────────────────────────────────────
        # Prints one overwriting line: Raw | Smooth | Var | Vel | Stable | Score | State
        # rep_state is not available here; state is derived from status for display
        _terminal_state = (
            "holding"  if status == "Correct" and not self._strain_flag else
            "moving"   if status == "Partial" else
            "rest"
        )
        LiveMetricsPrinter.print(
            raw_angle=round(raw_angle, 1),
            smoothed_angle=round(angle, 1),
            metrics=angle_metrics,
            form_score=form_score,
            state=_terminal_state,
            lean=lean,
        )

        return {
            # ── Existing fields (unchanged) ───────────────────────────────────
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
            # ── New fields ────────────────────────────────────────────────────
            "form_score":     form_score,       # {total, grade, breakdown}
            "angle_metrics":  angle_metrics,    # {variance, velocity, is_stable, is_smooth}
            "torso_lean":     lean,             # {lean_angle, is_leaning, direction}
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
            "form_score":    {"total": 0, "grade": "Needs Improvement", "breakdown": {}},
            "angle_metrics": {"variance": 0.0, "velocity": 0.0, "is_stable": True, "is_smooth": True},
            "torso_lean":    {"lean_angle": 0.0, "is_leaning": False, "direction": "upright"},
        }
