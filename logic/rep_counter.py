"""
logic/rep_counter.py
State-machine repetition counter.

One rep = transition through:  Incorrect/Partial → Correct → Incorrect/Partial
"""


class RepCounter:
    """
    Tracks exercise repetitions via posture-state transitions.

    States:
        "idle"    — waiting for first Correct phase
        "up"      — currently in Correct zone (rep in progress)
    """

    def __init__(self):
        self.reps: int = 0
        self._state: str = "idle"
        self._consecutive_correct: int = 0   # debounce: require N frames before counting
        self._DEBOUNCE = 3                   # frames needed to confirm state change

    def update(self, status: str) -> int:
        """
        Feed current frame status and return updated rep count.

        Args:
            status: "Correct" | "Partial" | "Incorrect"
        Returns:
            Current total rep count.
        """
        is_correct = status == "Correct"

        if self._state == "idle":
            if is_correct:
                self._consecutive_correct += 1
                if self._consecutive_correct >= self._DEBOUNCE:
                    self._state = "up"
                    self._consecutive_correct = 0
            else:
                self._consecutive_correct = 0

        elif self._state == "up":
            if not is_correct:
                # Rep completed — arm left the correct zone
                self.reps += 1
                self._state = "idle"
                self._consecutive_correct = 0

        return self.reps

    def reset(self) -> None:
        self.reps = 0
        self._state = "idle"
        self._consecutive_correct = 0
