"""
logic/session.py

Rehab session tracker — records per-frame data and produces a
structured physiotherapy progress report saved as JSON.

Tracks:
  - Total reps completed with full hold
  - Peak angle achieved (ROM progress indicator)
  - Strain/pain events
  - Time spent in each status zone
  - Average hold duration
  - Session duration
"""

import json
import os
import time
from datetime import datetime


class SessionTracker:

    _LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))

    def __init__(self, exercise_name: str, stage: int = 0):
        self.exercise_name  = exercise_name
        self.stage          = stage
        self._start_time    = time.time()
        self._active        = True

        # Angle tracking
        self._angles:       list[float] = []
        self._peak_angle:   float       = 0.0

        # Status zone time tracking (frames)
        self._zone_counts:  dict[str, int] = {
            "Correct": 0, "Partial": 0, "Rest": 0,
            "Warning": 0, "Incorrect": 0,
        }
        self._total_detected: int = 0

        # Rep / hold tracking
        self._reps:          int   = 0
        self._strain_events: int   = 0

    # ── Per-frame update ──────────────────────────────────────────────────────

    def update(self, angle: float | None, status: str | None,
               rep_state: dict) -> None:
        """
        Record one frame.

        Args:
            angle:     smoothed angle (None if not detected).
            status:    classification status string.
            rep_state: dict from RepCounter.update().
        """
        if not self._active:
            return

        self._reps          = rep_state.get("reps", 0)
        self._strain_events = rep_state.get("strain_events", 0)

        if angle is not None and status is not None:
            self._angles.append(angle)
            self._total_detected += 1
            self._peak_angle = max(self._peak_angle, angle)

            zone = status if status in self._zone_counts else "Incorrect"
            self._zone_counts[zone] += 1

    # ── Metrics ───────────────────────────────────────────────────────────────

    def get_summary(self) -> dict:
        duration   = round(time.time() - self._start_time, 1)
        avg_angle  = round(sum(self._angles) / len(self._angles), 1) \
                     if self._angles else 0.0
        total      = self._total_detected or 1
        correct_pct = round(self._zone_counts["Correct"] / total * 100, 1)

        # ROM quality: how close did the patient get to the correct zone
        rom_quality = "Poor"
        if self._zone_counts["Correct"] / total > 0.4:
            rom_quality = "Good"
        elif self._zone_counts["Partial"] / total > 0.3:
            rom_quality = "Fair"

        return {
            "exercise":       self.exercise_name,
            "stage":          self.stage,
            "total_reps":     self._reps,
            "peak_angle":     round(self._peak_angle, 1),
            "average_angle":  avg_angle,
            "accuracy_pct":   correct_pct,
            "rom_quality":    rom_quality,
            "strain_events":  self._strain_events,
            "duration_sec":   duration,
            "frames_tracked": self._total_detected,
            "zone_breakdown": {
                k: round(v / total * 100, 1)
                for k, v in self._zone_counts.items()
            },
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self) -> str:
        self._active = False
        os.makedirs(self._LOG_DIR, exist_ok=True)
        summary = self.get_summary()
        summary["timestamp"] = datetime.now().isoformat()

        # Rehab progress note for the report
        summary["progress_note"] = self._generate_note(summary)

        filename = (
            f"{self.exercise_name}_stage{self.stage}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        path = os.path.abspath(os.path.join(self._LOG_DIR, filename))
        with open(path, "w") as f:
            json.dump(summary, f, indent=2)
        return path

    def reset(self, exercise_name: str | None = None, stage: int = 0) -> None:
        if exercise_name:
            self.exercise_name = exercise_name
        self.stage           = stage
        self._start_time     = time.time()
        self._angles.clear()
        self._peak_angle     = 0.0
        self._zone_counts    = {k: 0 for k in self._zone_counts}
        self._total_detected = 0
        self._reps           = 0
        self._strain_events  = 0
        self._active         = True

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _generate_note(s: dict) -> str:
        """Generate a plain-English rehab progress note."""
        lines = []
        if s["strain_events"] > 2:
            lines.append("⚠ Multiple strain events — consider reducing stage difficulty.")
        if s["peak_angle"] < 20:
            lines.append("ROM is very limited — continue Stage 1 exercises.")
        elif s["peak_angle"] < 60:
            lines.append("ROM improving — maintain current stage.")
        else:
            lines.append("Good ROM achieved — consider advancing to next stage.")
        if s["total_reps"] >= 5 and s["accuracy_pct"] > 60:
            lines.append("Consistent performance — patient is progressing well.")
        elif s["total_reps"] == 0:
            lines.append("No complete reps recorded — encourage patient to hold position.")
        return " ".join(lines)
