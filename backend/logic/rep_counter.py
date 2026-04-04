"""
logic/rep_counter.py

Rehab-aware repetition counter with hold timer, rest detection,
and form-quality gating.

Changes from previous version:
  - update() now accepts form_score (int 0–100) from FormScorer
  - The "holding" state only starts when form_score >= FORM_GATE (default 50)
  - If form drops below gate mid-hold, the hold resets (prevents cheating)
  - form_score is included in the payload for the frontend
"""

import time

# Minimum form score required to enter / maintain the holding state.
# Below this, the patient must improve their form before a rep can be counted.
_FORM_GATE = 50


class RepCounter:
    """
    State machine for rehab rep counting.

    States:
        rest     — patient at rest / below partial range
        moving   — patient in partial zone, approaching target
        holding  — patient in correct zone WITH acceptable form, accumulating hold
        complete — hold time met, rep counted, waiting for return to rest
    """

    def __init__(self, hold_sec: float = 2.0):
        self.reps:          int   = 0
        self.strain_events: int   = 0
        self.hold_sec:      float = hold_sec

        self._state:        str         = "rest"
        self._hold_start:   float|None  = None
        self._hold_elapsed: float       = 0.0
        self._DEBOUNCE:     int         = 5
        self._consec:       int         = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, status: str, strain_warning: bool = False,
               form_score: int = 100) -> dict:
        """
        Feed current frame status and return rep state dict.

        Args:
            status:         "Correct" | "Partial" | "Rest" | "Warning" | "Incorrect"
            strain_warning: True if sudden angle drop detected
            form_score:     0–100 from FormScorer.compute()["total"]
                            Rep only counts when score >= _FORM_GATE

        Returns:
            dict: reps, hold_progress, state, strain_events, form_score
        """
        # Strain always resets everything — safety first
        if strain_warning:
            self.strain_events += 1
            self._state        = "rest"
            self._hold_start   = None
            self._hold_elapsed = 0.0
            self._consec       = 0
            return self._payload(form_score)

        good_form = form_score >= _FORM_GATE

        if self._state == "rest":
            if status in ("Partial", "Correct"):
                self._consec += 1
                if self._consec >= self._DEBOUNCE:
                    self._state  = "moving"
                    self._consec = 0
            else:
                self._consec = 0

        elif self._state == "moving":
            if status == "Correct" and good_form:
                # Only enter holding if form is acceptable
                self._consec += 1
                if self._consec >= self._DEBOUNCE:
                    self._state      = "holding"
                    self._hold_start = time.time()
                    self._consec     = 0
            elif status in ("Rest", "Incorrect"):
                self._state  = "rest"
                self._consec = 0
            # Stay in moving if Partial or Correct-but-poor-form

        elif self._state == "holding":
            if status == "Correct" and good_form:
                # Continue accumulating hold time
                self._hold_elapsed = time.time() - (self._hold_start or time.time())
                if self._hold_elapsed >= self.hold_sec:
                    self.reps          += 1
                    self._state         = "complete"
                    self._hold_start    = None
                    self._hold_elapsed  = 0.0
            else:
                # Left correct zone OR form dropped below gate — reset hold
                # (prevents patient from cheating by leaning or shaking through)
                self._state        = "moving" if status == "Partial" else "rest"
                self._hold_start   = None
                self._hold_elapsed = 0.0

        elif self._state == "complete":
            if status in ("Rest", "Incorrect"):
                self._state  = "rest"
                self._consec = 0

        return self._payload(form_score)

    def set_hold_sec(self, hold_sec: float) -> None:
        self.hold_sec = hold_sec

    def reset(self) -> None:
        self.reps           = 0
        self.strain_events  = 0
        self._state         = "rest"
        self._hold_start    = None
        self._hold_elapsed  = 0.0
        self._consec        = 0

    # ── Internal ──────────────────────────────────────────────────────────────

    def _payload(self, form_score: int = 0) -> dict:
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
            "form_score":    form_score,   # passed through for frontend display
        }
