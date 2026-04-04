"""
logic/angle.py
Angle calculation, jitter-smoothing, and movement-quality metrics.
"""

import numpy as np
from collections import deque


def calculate_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """
    Compute the angle (degrees) at vertex b formed by vectors b→a and b→c.

    Args:
        a: [x, y] first point  (e.g. shoulder)
        b: [x, y] vertex point (e.g. elbow)
        c: [x, y] third point  (e.g. wrist)
    Returns:
        Angle in degrees, clamped to [0, 180].
    """
    ba = a - b
    bc = c - b
    denom = np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6
    cosine = np.dot(ba, bc) / denom
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


class AngleSmoother:
    """
    Moving-average smoother for a single angle stream.
    Reduces per-frame jitter without introducing significant lag.
    """

    def __init__(self, window: int = 7):
        self._buf: deque = deque(maxlen=window)

    def update(self, angle: float) -> float:
        """Push a new raw angle and return the smoothed value."""
        self._buf.append(angle)
        return float(np.mean(self._buf))

    def reset(self):
        self._buf.clear()

    @property
    def buffer(self) -> list:
        """Return current buffer contents as a list (oldest → newest)."""
        return list(self._buf)


class LiveMetricsPrinter:
    """
    Prints a single-line live metrics dashboard to the terminal.
    Overwrites the same line each frame using carriage return.
    """
    _G  = "\033[92m"
    _Y  = "\033[93m"
    _R  = "\033[91m"
    _B  = "\033[94m"
    _NC = "\033[0m"

    @staticmethod
    def _grade_color(score: int) -> str:
        C = LiveMetricsPrinter
        if score >= 85: return C._G
        if score >= 60: return C._Y
        return C._R

    @staticmethod
    def print(raw_angle: float, smoothed_angle: float,
              metrics: dict, form_score: dict,
              state: str, lean: dict) -> None:
        """
        Print one overwriting line of live metrics.

        Args:
            raw_angle:      unsmoothed angle from calculate_angle()
            smoothed_angle: output of AngleSmoother.update()
            metrics:        output of AngleMetrics.update()
            form_score:     output of FormScorer.compute()
            state:          rep counter state string
            lean:           output of BodyAnalyzer.compute_torso_lean()
        """
        C  = LiveMetricsPrinter
        nc = C._NC
        deg = chr(176)

        variance = metrics.get("variance", 0.0)
        velocity = metrics.get("velocity", 0.0)
        score    = form_score.get("total", 0)
        grade    = form_score.get("grade", "")
        lean_ang = lean.get("lean_angle", 0.0)
        leaning  = lean.get("is_leaning", False)

        stable_tag = f"{C._G}STABLE{nc}" if metrics.get("is_stable") else f"{C._R}SHAKY{nc}"
        smooth_tag = f"{C._G}SMOOTH{nc}" if metrics.get("is_smooth") else f"{C._R}JERKY{nc}"
        lean_tag   = f"{C._R}LEAN {lean_ang:.1f}{deg}{nc}" if leaning else f"{C._G}UPRIGHT{nc}"
        sc         = {"rest": nc, "moving": C._Y, "holding": C._B, "complete": C._G}.get(state, nc)
        score_col  = C._grade_color(score)

        print(
            f"  Raw:{C._Y}{raw_angle:6.1f}{deg}{nc} "
            f"Smooth:{C._G}{smoothed_angle:6.1f}{deg}{nc} "
            f"Var:{C._Y}{variance:5.1f}{nc} "
            f"Vel:{C._Y}{velocity:4.1f}{nc} "
            f"{stable_tag} {smooth_tag} {lean_tag} "
            f"Score:{score_col}{score:3d}{nc}({grade}) "
            f"State:{sc}{state.upper():<8}{nc}",
            end="\r", flush=True
        )


class AngleMetrics:
    """
    Computes movement-quality metrics from a rolling angle history.

    Metrics:
        stability  — low variance = steady hold (0.0 = perfect, higher = shaky)
        velocity   — angular speed deg/frame (0.0 = still, higher = faster)
        is_stable  — True when variance is below threshold
        is_smooth  — True when velocity spike is below threshold
    """

    # Variance above this → unstable (shaky hold)
    _VARIANCE_THRESHOLD  = 8.0   # deg²
    # Per-frame velocity above this → jerky movement
    _VELOCITY_THRESHOLD  = 6.0   # deg/frame

    def __init__(self, window: int = 10):
        # Separate buffer so metrics use a slightly wider window than smoother
        self._buf: deque = deque(maxlen=window)

    def update(self, smoothed_angle: float) -> dict:
        """
        Push the latest smoothed angle and return quality metrics.

        Args:
            smoothed_angle: output of AngleSmoother.update()
        Returns:
            dict with: variance, velocity, is_stable, is_smooth
        """
        self._buf.append(smoothed_angle)
        arr = np.array(self._buf)

        # Stability: variance of angle over the window
        variance = float(np.var(arr)) if len(arr) > 1 else 0.0

        # Smoothness: absolute angular velocity (change between last two frames)
        velocity = abs(float(arr[-1] - arr[-2])) if len(arr) >= 2 else 0.0

        return {
            "variance":  round(variance, 2),
            "velocity":  round(velocity, 2),
            "is_stable": variance  < self._VARIANCE_THRESHOLD,
            "is_smooth": velocity  < self._VELOCITY_THRESHOLD,
        }

    def reset(self):
        self._buf.clear()
