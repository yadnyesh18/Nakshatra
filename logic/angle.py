"""
logic/angle.py
Angle calculation and jitter-smoothing utilities.
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
