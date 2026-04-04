"""
logic/rep_counter.py

Rehab-aware repetition counter with hold timer and rest detection.

For physiotherapy patients:
  - A rep requires the patient to HOLD the correct position for hold_sec seconds
  - Rest periods between reps are expected and tracked
  - Strain/warning events are recorded separately
  - Debounce is generous (patients move slowly)
"""

import time


class RepCounter:
    """
    State machine for rehab rep counting.

    States:
        rest     — patient at rest / below partial range
        moving   — patient in partial zone, approaching target
        holding  — patient in correct zone, accumulating hold time
        complete — hold time met, rep counted, waiting for return to rest
    """

    def __init__(self, hold_sec: float = 2.0):
        self.reps:          int   = 0
        self.strain_events: int   = 0
        self.hold_sec:      float = hold_sec   # required hold duration

        self._state:        str   = "rest"
        self._hold_start:   float | None = None
        self._hold_elapsed: float = 0.0        # seconds held so far this rep

        # Debounce: require N consecutive frames before state transition
        # Generous for slow patient movements
        self._DEBOUNCE      = 5
        self._consec:       int   = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, status: str, strain_warning: bool = False) -> dict:
        """
        Feed current frame status and return rep state dict.

        Args:
            status:         "Correct" | "Partial" | "Rest" | "Warning" | "Incorrect"
            strain_warning: True if body_analyzer detected sudden angle drop

        Returns:
            dict with: reps, hold_progress (0.0–1.0), state, strain_events
        """
        if strain_warning:
            self.strain_events += 1
            # Reset hold — patient must restart the hold after a strain event
            self._state      = "rest"
            self._hold_start = None
            self._hold_elapsed = 0.0
            self._consec     = 0
            return self._payload()

        if self._state == "rest":
            if status in ("Partial", "Correct"):
                self._consec += 1
                if self._consec >= self._DEBOUNCE:
                    self._state  = "moving"
                    self._consec = 0
            else:
                self._consec = 0

        elif self._state == "moving":
            if status == "Correct":
                self._consec += 1
                if self._consec >= self._DEBOUNCE:
                    self._state      = "holding"
                    self._hold_start = time.time()
                    self._consec     = 0
            elif status in ("Rest", "Incorrect"):
                # Fell back before reaching target
                self._state  = "rest"
                self._consec = 0
            # stay in moving if Partial

        elif self._state == "holding":
            if status == "Correct":
                self._hold_elapsed = time.time() - (self._hold_start or time.time())
                if self._hold_elapsed >= self.hold_sec:
                    # Hold complete — count the rep
                    self.reps       += 1
                    self._state      = "complete"
                    self._hold_start = None
                    self._hold_elapsed = 0.0
            else:
                # Left correct zone before hold completed — reset hold
                self._state        = "moving" if status == "Partial" else "rest"
                self._hold_start   = None
                self._hold_elapsed = 0.0

        elif self._state == "complete":
            # Wait for patient to return to rest before next rep
            if status in ("Rest", "Incorrect"):
                self._state  = "rest"
                self._consec = 0

        return self._payload()

    def set_hold_sec(self, hold_sec: float) -> None:
        """Update required hold duration (called when exercise/stage changes)."""
        self.hold_sec = hold_sec

    def reset(self) -> None:
        self.reps           = 0
        self.strain_events  = 0
        self._state         = "rest"
        self._hold_start    = None
        self._hold_elapsed  = 0.0
        self._consec        = 0

    # ── Internal ──────────────────────────────────────────────────────────────

    def _payload(self) -> dict:
        progress = 0.0
        if self._state == "holding" and self.hold_sec > 0:
            progress = min(1.0, self._hold_elapsed / self.hold_sec)
        elif self._state == "complete":
            progress = 1.0

        return {
            "reps":          self.reps,
            "hold_progress": round(progress, 2),
            "state":         self._state,
            "strain_events": self.strain_events,
        }
