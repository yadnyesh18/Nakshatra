"""
logic/session.py
Session tracking — aggregates per-frame data into session-level metrics
and persists results to a JSON log file.
"""

import json
import os
import time
from datetime import datetime


class SessionTracker:
    """
    Accumulates per-frame posture data and computes session metrics.

    Metrics tracked:
        - total_reps
        - average_angle
        - accuracy  (% of detected frames where status == "Correct")
        - duration  (seconds)
    """

    _LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")

    def __init__(self, exercise_name: str):
        self.exercise_name = exercise_name
        self._start_time: float = time.time()
        self._angles: list[float] = []
        self._correct_frames: int = 0
        self._total_detected: int = 0
        self._reps: int = 0
        self._active: bool = True

    # ── Per-frame update ──────────────────────────────────────────────────────

    def update(self, angle: float | None, status: str | None, reps: int) -> None:
        """
        Record one frame of data.

        Args:
            angle:  smoothed angle value (None if not detected).
            status: "Correct" | "Partial" | "Incorrect" | None.
            reps:   current rep count from RepCounter.
        """
        if not self._active:
            return
        self._reps = reps
        if angle is not None and status is not None:
            self._angles.append(angle)
            self._total_detected += 1
            if status == "Correct":
                self._correct_frames += 1

    # ── Metrics ───────────────────────────────────────────────────────────────

    def get_summary(self) -> dict:
        """Return current session metrics as a plain dict (JSON-serialisable)."""
        duration = round(time.time() - self._start_time, 1)
        avg_angle = round(sum(self._angles) / len(self._angles), 1) if self._angles else 0.0
        accuracy = (
            round(self._correct_frames / self._total_detected * 100, 1)
            if self._total_detected > 0 else 0.0
        )
        return {
            "exercise":      self.exercise_name,
            "total_reps":    self._reps,
            "average_angle": avg_angle,
            "accuracy_pct":  accuracy,
            "duration_sec":  duration,
            "frames_tracked": self._total_detected,
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self) -> str:
        """
        Write session summary to a timestamped JSON file in logs/.

        Returns:
            Absolute path of the written file.
        """
        self._active = False
        os.makedirs(self._LOG_DIR, exist_ok=True)
        summary = self.get_summary()
        summary["timestamp"] = datetime.now().isoformat()

        filename = (
            f"{self.exercise_name}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        path = os.path.abspath(os.path.join(self._LOG_DIR, filename))
        with open(path, "w") as f:
            json.dump(summary, f, indent=2)
        return path

    def reset(self, exercise_name: str | None = None) -> None:
        """Restart session, optionally switching exercise."""
        if exercise_name:
            self.exercise_name = exercise_name
        self._start_time = time.time()
        self._angles.clear()
        self._correct_frames = 0
        self._total_detected = 0
        self._reps = 0
        self._active = True
