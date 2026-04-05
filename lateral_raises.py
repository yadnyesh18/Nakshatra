"""
lateral_raises.py
=================
Real-time left-arm Lateral Raises exercise tracker.

Tracks the angle at the left shoulder (hip → shoulder → wrist).
    • Arm at side  →  ~0°   →  Relaxed (Red)
    • Arm raised   →  75–90° →  Stretched (Green)

Workout: 3 sets × 10 reps — hold stretched for 2s to count a rep.

Usage
-----
    python lateral_raises.py
    python lateral_raises.py --camera 1
    python lateral_raises.py --gif /path/to/demo.gif

Press 'q' or ESC to quit. Press 'e' to exit set early.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks.python import vision as mp_vision
from mediapipe.tasks.python.vision import (
    PoseLandmarker,
    PoseLandmarkerOptions,
    RunningMode,
)


# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────

# Landmarks: angle at SHOULDER between HIP and WRIST
LEFT_HIP      = 23
LEFT_SHOULDER = 11
LEFT_WRIST    = 15

# Angle thresholds (degrees)
# Arm at side ≈ 10–20°, arm raised ≈ 75–90°
RELAXED_ANGLE   = 25     # below this → Relaxed (arm at side)
STRETCHED_ANGLE = 75     # above this → Stretched (arm raised)

# Workout
REPS_PER_SET    = 10
TOTAL_SETS      = 3
COOLDOWN_SECS   = 30
HOLD_DURATION   = 2.0

# EMA
EMA_ALPHA = 0.4

# Colors (BGR)
COLOR_RED        = (0, 0, 255)
COLOR_GREEN      = (0, 255, 0)
COLOR_YELLOW     = (0, 255, 255)
COLOR_WHITE      = (255, 255, 255)
COLOR_DARK_BG    = (30, 30, 30)
COLOR_CYAN       = (255, 255, 0)
COLOR_BAR_BG     = (60, 60, 60)
COLOR_BAR_FILL   = (0, 220, 100)
COLOR_BAR_DONE   = (0, 255, 0)
COLOR_COOLDOWN   = (255, 180, 50)

# Drawing
LINE_THICKNESS = 6
CIRCLE_RADIUS  = 10
FONT           = cv2.FONT_HERSHEY_SIMPLEX

# GIF panel
GIF_PANEL_WIDTH  = 200
GIF_PANEL_HEIGHT = 200

# Model
MODEL_DIR  = Path(__file__).parent / "models"
MODEL_PATH = MODEL_DIR / "pose_landmarker_full.task"
MODEL_URL  = (
    "https://storage.googleapis.com/mediapipe-models/"
    "pose_landmarker/pose_landmarker_full/float16/1/"
    "pose_landmarker_full.task"
)


# ──────────────────────────────────────────────────────────────
# Model download
# ──────────────────────────────────────────────────────────────

def ensure_model(model_path: Path = MODEL_PATH) -> str:
    model_path.parent.mkdir(parents=True, exist_ok=True)
    if not model_path.exists():
        print(f"[INFO] Downloading pose model → {model_path} ...")
        try:
            urllib.request.urlretrieve(MODEL_URL, str(model_path))
            print("[INFO] Download complete.")
        except Exception as e:
            print(f"[ERROR] Failed to download model: {e}")
            sys.exit(1)
    return str(model_path)


# ──────────────────────────────────────────────────────────────
# Angle calculation
# ──────────────────────────────────────────────────────────────

def compute_shoulder_angle(
    hip: np.ndarray,
    shoulder: np.ndarray,
    wrist: np.ndarray,
) -> float:
    """
    Compute the angle at the shoulder joint (vertex) formed by
    hip → shoulder → wrist.

    When the arm hangs at the side, hip-shoulder-wrist is roughly collinear
    giving ~0–20°. When the arm is raised laterally to horizontal, ~90°.
    """
    sh = hip - shoulder       # vector from shoulder to hip (torso direction)
    sw = wrist - shoulder     # vector from shoulder to wrist (arm direction)

    norm_sh = np.linalg.norm(sh)
    norm_sw = np.linalg.norm(sw)

    if norm_sh < 1e-9 or norm_sw < 1e-9:
        return 0.0

    cos_angle = np.dot(sh, sw) / (norm_sh * norm_sw)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


# ──────────────────────────────────────────────────────────────
# EMA Smoother
# ──────────────────────────────────────────────────────────────

class EMASmoother:
    def __init__(self, alpha: float = EMA_ALPHA) -> None:
        self.alpha = alpha
        self._value: float | None = None

    def update(self, new_value: float) -> float:
        if self._value is None:
            self._value = new_value
        else:
            self._value = self.alpha * new_value + (1 - self.alpha) * self._value
        return self._value

    def reset(self) -> None:
        self._value = None

    @property
    def value(self) -> float:
        return self._value if self._value is not None else 0.0


# ──────────────────────────────────────────────────────────────
# State Machine with Hold Timer
# ──────────────────────────────────────────────────────────────

class ExerciseStateMachine:
    """
    State machine for lateral raises.

    NOTE: For lateral raises the logic is INVERTED compared to elbow stretching:
        - LOW angle (<25°) = Relaxed (arm at side)
        - HIGH angle (>75°) = Stretched (arm raised)

    RELAXED → RAISING → HOLDING → STRETCHED → LOWERING → RELAXED (+1 rep)
    """

    RELAXED   = "RELAXED"
    RAISING   = "RAISING"
    HOLDING   = "HOLDING"
    STRETCHED = "STRETCHED"
    LOWERING  = "LOWERING"

    def __init__(self) -> None:
        self.state = self.RELAXED
        self.reps = 0
        self.peak_angle: float = 0.0       # highest angle in current set (best raise)
        self.all_angles: list[float] = []
        self._hold_start: float | None = None
        self.hold_progress: float = 0.0

    def reset_for_new_set(self) -> None:
        self.state = self.RELAXED
        self.reps = 0
        self.peak_angle = 0.0
        self.all_angles.clear()
        self._hold_start = None
        self.hold_progress = 0.0

    @property
    def avg_angle(self) -> float:
        return float(np.mean(self.all_angles)) if self.all_angles else 0.0

    @property
    def best_peak_angle(self) -> float:
        """Highest angle reached (best raise) in current set."""
        return self.peak_angle

    def update(self, angle: float) -> str:
        self.all_angles.append(angle)
        self.peak_angle = max(self.peak_angle, angle)

        if self.state == self.RELAXED:
            self.hold_progress = 0.0
            self._hold_start = None
            if angle > RELAXED_ANGLE:
                self.state = self.RAISING

        elif self.state == self.RAISING:
            self.hold_progress = 0.0
            if angle >= STRETCHED_ANGLE:
                self.state = self.HOLDING
                self._hold_start = time.monotonic()
            elif angle <= RELAXED_ANGLE:
                self.state = self.RELAXED

        elif self.state == self.HOLDING:
            if angle < STRETCHED_ANGLE:
                self.state = self.RAISING
                self._hold_start = None
                self.hold_progress = 0.0
            else:
                elapsed = time.monotonic() - self._hold_start
                self.hold_progress = min(elapsed / HOLD_DURATION, 1.0)
                if elapsed >= HOLD_DURATION:
                    self.state = self.STRETCHED
                    self.hold_progress = 1.0

        elif self.state == self.STRETCHED:
            if angle < STRETCHED_ANGLE:
                self.state = self.LOWERING

        elif self.state == self.LOWERING:
            if angle <= RELAXED_ANGLE:
                self.state = self.RELAXED
                self.reps += 1
                self.hold_progress = 0.0
                self._hold_start = None
            elif angle >= STRETCHED_ANGLE:
                self.state = self.HOLDING
                self._hold_start = time.monotonic()

        return self.state


# ──────────────────────────────────────────────────────────────
# GIF Loader
# ──────────────────────────────────────────────────────────────

class GifPlayer:
    def __init__(self, gif_path: str, width: int, height: int) -> None:
        self.frames: list[np.ndarray] = []
        self.idx = 0
        self.width = width
        self.height = height
        self._last_advance = time.monotonic()
        self._frame_delay = 0.08

        cap = cv2.VideoCapture(gif_path)
        if not cap.isOpened():
            print(f"[WARN] Cannot open GIF: {gif_path}")
            return
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
            self.frames.append(resized)
        cap.release()
        if self.frames:
            print(f"[INFO] Loaded GIF: {len(self.frames)} frames")

    @property
    def available(self) -> bool:
        return len(self.frames) > 0

    def get_frame(self) -> np.ndarray | None:
        if not self.frames:
            return None
        now = time.monotonic()
        if now - self._last_advance >= self._frame_delay:
            self.idx = (self.idx + 1) % len(self.frames)
            self._last_advance = now
        return self.frames[self.idx]


# ──────────────────────────────────────────────────────────────
# Drawing helpers
# ──────────────────────────────────────────────────────────────

def get_angle_color(angle: float) -> tuple[int, int, int]:
    """Color based on angle — inverted compared to elbow stretching."""
    if angle <= RELAXED_ANGLE:
        return COLOR_RED       # arm at side
    elif angle >= STRETCHED_ANGLE:
        return COLOR_GREEN     # arm raised
    return COLOR_YELLOW        # transitioning


def draw_arm_overlay(frame, hip_px, shoulder_px, wrist_px, color, angle):
    """Draw torso line (hip→shoulder) and arm line (shoulder→wrist)."""
    # Torso reference line (dimmer)
    cv2.line(frame, hip_px, shoulder_px, (100, 100, 100), 3)

    # Arm line (bright, color-coded)
    cv2.line(frame, shoulder_px, wrist_px, color, LINE_THICKNESS)

    # Landmark circles
    cv2.circle(frame, hip_px, CIRCLE_RADIUS - 2, (100, 100, 100), cv2.FILLED)
    cv2.circle(frame, shoulder_px, CIRCLE_RADIUS + 2, color, cv2.FILLED)
    cv2.circle(frame, wrist_px, CIRCLE_RADIUS, color, cv2.FILLED)

    # Angle text near shoulder
    text_pos = (shoulder_px[0] + 15, shoulder_px[1] - 20)
    cv2.putText(frame, f"{angle:.1f}", text_pos, FONT, 0.8,
                COLOR_WHITE, 3, cv2.LINE_AA)
    cv2.putText(frame, f"{angle:.1f}", text_pos, FONT, 0.8,
                color, 2, cv2.LINE_AA)


def draw_hold_bar(frame, progress, x, y, bar_width=260, bar_height=22):
    cv2.putText(frame, "HOLD", (x, y - 6), FONT, 0.5, COLOR_WHITE, 1, cv2.LINE_AA)
    cv2.rectangle(frame, (x, y), (x + bar_width, y + bar_height), COLOR_BAR_BG, cv2.FILLED)
    fill_w = int(bar_width * progress)
    fill_color = COLOR_BAR_DONE if progress >= 1.0 else COLOR_BAR_FILL
    if fill_w > 0:
        cv2.rectangle(frame, (x, y), (x + fill_w, y + bar_height), fill_color, cv2.FILLED)
    cv2.rectangle(frame, (x, y), (x + bar_width, y + bar_height), COLOR_WHITE, 1)
    pct = f"{int(progress * 100)}%"
    cv2.putText(frame, pct, (x + bar_width // 2 - 15, y + bar_height - 5),
                FONT, 0.5, COLOR_WHITE, 1, cv2.LINE_AA)
    if progress >= 1.0:
        cv2.putText(frame, "REP COUNTED!", (x + bar_width + 10, y + bar_height - 3),
                    FONT, 0.6, COLOR_GREEN, 2, cv2.LINE_AA)


def draw_hud(frame, sm, angle, color, current_set, total_sets):
    h, w = frame.shape[:2]
    panel_w, panel_h = 310, 275

    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (panel_w, panel_h), COLOR_DARK_BG, cv2.FILLED)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)

    y = 28

    # Title
    cv2.putText(frame, "LATERAL RAISES", (12, y), FONT, 0.7, COLOR_WHITE, 2, cv2.LINE_AA)
    y += 8
    cv2.line(frame, (12, y), (panel_w - 12, y), (80, 80, 80), 1)
    y += 22

    # Set
    cv2.putText(frame, f"Set {current_set} / {total_sets}", (12, y), FONT, 0.6,
                COLOR_COOLDOWN, 2, cv2.LINE_AA)
    y += 30

    # State
    cv2.circle(frame, (22, y - 5), 8, color, cv2.FILLED)
    cv2.putText(frame, f"{sm.state}", (38, y), FONT, 0.6, color, 2, cv2.LINE_AA)
    y += 32

    # Reps
    cv2.putText(frame, "Reps", (12, y), FONT, 0.5, (160, 160, 160), 1, cv2.LINE_AA)
    cv2.putText(frame, f"{sm.reps} / {REPS_PER_SET}", (120, y), FONT, 0.7,
                COLOR_CYAN, 2, cv2.LINE_AA)
    y += 30

    # Peak angle (this set — highest raise)
    cv2.putText(frame, "Peak Angle", (12, y), FONT, 0.5, (160, 160, 160), 1, cv2.LINE_AA)
    cv2.putText(frame, f"{sm.peak_angle:.1f}", (140, y), FONT, 0.7,
                (100, 255, 200), 2, cv2.LINE_AA)
    y += 30

    # Avg angle
    cv2.putText(frame, "Avg Angle", (12, y), FONT, 0.5, (160, 160, 160), 1, cv2.LINE_AA)
    cv2.putText(frame, f"{sm.avg_angle:.1f}", (140, y), FONT, 0.7,
                (200, 200, 100), 2, cv2.LINE_AA)
    y += 30

    # Current angle
    cv2.putText(frame, "Angle", (12, y), FONT, 0.5, (160, 160, 160), 1, cv2.LINE_AA)
    cv2.putText(frame, f"{angle:.1f}", (140, y), FONT, 0.7,
                (200, 200, 200), 2, cv2.LINE_AA)

    # Hold bar
    if sm.state == ExerciseStateMachine.HOLDING or sm.hold_progress > 0:
        draw_hold_bar(frame, sm.hold_progress, x=12, y=panel_h + 10)

    # Bottom
    cv2.putText(frame, "'q'/ESC = quit  |  'e' = exit set early",
                (w // 2 - 210, h - 12), FONT, 0.45, (120, 120, 120), 1, cv2.LINE_AA)


def draw_gif_panel(frame, gif_frame, panel_w, panel_h):
    if gif_frame is None:
        return
    h, w = frame.shape[:2]
    margin = 10
    x1, y1 = w - panel_w - margin, margin
    x2, y2 = x1 + panel_w, y1 + panel_h

    cv2.rectangle(frame, (x1 - 2, y1 - 22), (x2 + 2, y2 + 2), COLOR_DARK_BG, cv2.FILLED)
    cv2.putText(frame, "DEMO", (x1 + 5, y1 - 5), FONT, 0.5, COLOR_WHITE, 1, cv2.LINE_AA)

    gif_resized = cv2.resize(gif_frame, (panel_w, panel_h), interpolation=cv2.INTER_AREA)
    if gif_resized.shape[2] == 4:
        gif_resized = cv2.cvtColor(gif_resized, cv2.COLOR_BGRA2BGR)
    frame[y1:y2, x1:x2] = gif_resized


def draw_no_gif_placeholder(frame, panel_w, panel_h):
    h, w = frame.shape[:2]
    margin = 10
    x1, y1 = w - panel_w - margin, margin
    x2, y2 = x1 + panel_w, y1 + panel_h

    overlay = frame.copy()
    cv2.rectangle(overlay, (x1 - 2, y1 - 22), (x2 + 2, y2 + 2), COLOR_DARK_BG, cv2.FILLED)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
    cv2.putText(frame, "DEMO", (x1 + 5, y1 - 5), FONT, 0.5, COLOR_WHITE, 1, cv2.LINE_AA)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (80, 80, 80), 2)
    cv2.putText(frame, "No GIF", (x1 + panel_w // 2 - 30, y1 + panel_h // 2 - 5),
                FONT, 0.5, (100, 100, 100), 1, cv2.LINE_AA)
    cv2.putText(frame, "provided", (x1 + panel_w // 2 - 35, y1 + panel_h // 2 + 18),
                FONT, 0.5, (100, 100, 100), 1, cv2.LINE_AA)


# ──────────────────────────────────────────────────────────────
# Cooldown screen
# ──────────────────────────────────────────────────────────────

def draw_cooldown_screen(frame, remaining_secs: float, completed_set: int, total_sets: int):
    h, w = frame.shape[:2]
    frame[:] = (20, 20, 20)
    cx = w // 2

    cv2.putText(frame, "COOLDOWN", (cx - 120, h // 2 - 100),
                FONT, 1.5, COLOR_COOLDOWN, 3, cv2.LINE_AA)

    cv2.putText(frame, f"Set {completed_set} of {total_sets} complete!",
                (cx - 170, h // 2 - 40), FONT, 0.8, COLOR_WHITE, 2, cv2.LINE_AA)

    secs_left = max(0, int(math.ceil(remaining_secs)))
    cv2.putText(frame, f"{secs_left}", (cx - 30, h // 2 + 60),
                FONT, 3.0, COLOR_GREEN, 5, cv2.LINE_AA)
    cv2.putText(frame, "seconds", (cx - 55, h // 2 + 100),
                FONT, 0.8, (160, 160, 160), 2, cv2.LINE_AA)

    # Progress bar
    bar_w, bar_h = 400, 20
    bx = cx - bar_w // 2
    by = h // 2 + 130
    progress = max(0.0, min(1.0, 1.0 - remaining_secs / COOLDOWN_SECS))
    cv2.rectangle(frame, (bx, by), (bx + bar_w, by + bar_h), COLOR_BAR_BG, cv2.FILLED)
    fill = int(bar_w * progress)
    if fill > 0:
        cv2.rectangle(frame, (bx, by), (bx + fill, by + bar_h), COLOR_COOLDOWN, cv2.FILLED)
    cv2.rectangle(frame, (bx, by), (bx + bar_w, by + bar_h), COLOR_WHITE, 1)

    if completed_set < total_sets:
        cv2.putText(frame, f"Next: Set {completed_set + 1}", (cx - 80, by + 60),
                    FONT, 0.7, (130, 130, 130), 1, cv2.LINE_AA)

    cv2.putText(frame, "Press 'q' or ESC to quit", (cx - 130, h - 30),
                FONT, 0.5, (100, 100, 100), 1, cv2.LINE_AA)


# ──────────────────────────────────────────────────────────────
# Summary screen
# ──────────────────────────────────────────────────────────────

def draw_summary_screen(frame, set_results: list[dict], was_early_exit: bool):
    h, w = frame.shape[:2]
    frame[:] = (20, 20, 20)
    cx = w // 2

    title = "WORKOUT COMPLETE!" if not was_early_exit else "WORKOUT ENDED"
    title_color = COLOR_GREEN if not was_early_exit else COLOR_YELLOW
    cv2.putText(frame, title, (cx - 200, 60), FONT, 1.3, title_color, 3, cv2.LINE_AA)
    cv2.putText(frame, "LATERAL RAISES", (cx - 100, 100), FONT, 0.7, COLOR_WHITE, 2, cv2.LINE_AA)

    y = 150
    cv2.line(frame, (cx - 250, y), (cx + 250, y), (80, 80, 80), 1)
    y += 30
    cv2.putText(frame, "SET", (cx - 220, y), FONT, 0.6, (160, 160, 160), 1, cv2.LINE_AA)
    cv2.putText(frame, "REPS", (cx - 80, y), FONT, 0.6, (160, 160, 160), 1, cv2.LINE_AA)
    cv2.putText(frame, "PEAK ANGLE", (cx + 60, y), FONT, 0.6, (160, 160, 160), 1, cv2.LINE_AA)
    y += 10
    cv2.line(frame, (cx - 250, y), (cx + 250, y), (80, 80, 80), 1)
    y += 30

    peak_angles = []
    total_reps = 0
    for i, result in enumerate(set_results):
        reps = result["reps"]
        peak = result["peak_angle"]
        total_reps += reps
        if peak > 0.0:
            peak_angles.append(peak)

        set_color = COLOR_GREEN if reps >= REPS_PER_SET else COLOR_YELLOW
        cv2.putText(frame, f"Set {i + 1}", (cx - 220, y), FONT, 0.7, COLOR_WHITE, 2, cv2.LINE_AA)
        cv2.putText(frame, f"{reps}", (cx - 60, y), FONT, 0.7, set_color, 2, cv2.LINE_AA)
        peak_str = f"{peak:.1f}" if peak > 0.0 else "—"
        cv2.putText(frame, peak_str, (cx + 80, y), FONT, 0.7, (100, 255, 200), 2, cv2.LINE_AA)
        y += 40

    y += 5
    cv2.line(frame, (cx - 250, y), (cx + 250, y), (80, 80, 80), 1)
    y += 35

    cv2.putText(frame, "Total Reps:", (cx - 220, y), FONT, 0.7, (160, 160, 160), 1, cv2.LINE_AA)
    cv2.putText(frame, f"{total_reps}", (cx + 80, y), FONT, 0.8, COLOR_CYAN, 2, cv2.LINE_AA)
    y += 40

    if peak_angles:
        avg_peak = float(np.mean(peak_angles))
        cv2.putText(frame, "Avg Peak Angle:", (cx - 220, y), FONT, 0.7,
                    (160, 160, 160), 1, cv2.LINE_AA)
        cv2.putText(frame, f"{avg_peak:.1f}", (cx + 80, y), FONT, 0.8,
                    (100, 255, 200), 2, cv2.LINE_AA)

    cv2.putText(frame, "Press any key to exit", (cx - 110, h - 30),
                FONT, 0.6, (130, 130, 130), 1, cv2.LINE_AA)


# ──────────────────────────────────────────────────────────────
# Landmark helpers
# ──────────────────────────────────────────────────────────────

def extract_landmark_xy(landmarks, idx: int) -> np.ndarray:
    lm = landmarks[idx]
    return np.array([lm.x, lm.y], dtype=np.float64)


def normalized_to_pixel(point: np.ndarray, width: int, height: int) -> tuple[int, int]:
    return (int(point[0] * width), int(point[1] * height))


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lateral Raises — real-time shoulder raise tracker")
    parser.add_argument("--camera", type=int, default=0, help="Camera index (default: 0)")
    parser.add_argument("--model", type=str, default=None, help="Path to .task model file")
    parser.add_argument("--gif", type=str, default=None, help="Path to exercise demo GIF")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # ── Model ────────────────────────────────────────────────
    model_path = args.model if args.model else ensure_model()
    print(f"[INFO] Using model: {model_path}")

    base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
    options = PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.6,
        min_tracking_confidence=0.6,
        min_pose_presence_confidence=0.5,
        output_segmentation_masks=False,
    )
    landmarker = PoseLandmarker.create_from_options(options)

    # ── GIF ──────────────────────────────────────────────────
    gif_player: GifPlayer | None = None
    if args.gif and os.path.isfile(args.gif):
        gif_player = GifPlayer(args.gif, GIF_PANEL_WIDTH, GIF_PANEL_HEIGHT)
        if not gif_player.available:
            gif_player = None

    # ── Webcam ───────────────────────────────────────────────
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open camera {args.camera}")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    print(f"[INFO] Workout: {TOTAL_SETS} sets × {REPS_PER_SET} reps")
    print(f"[INFO] Hold raised position for {HOLD_DURATION}s to count a rep.")
    print("[INFO] Press 'e' to exit set early, 'q'/ESC to quit.\n")

    # ── Workout state ────────────────────────────────────────
    smoother = EMASmoother(alpha=EMA_ALPHA)
    sm = ExerciseStateMachine()
    start_ms = int(time.monotonic() * 1000)

    current_set = 1
    set_results: list[dict] = []
    was_early_exit = False
    phase = "workout"
    cooldown_start: float = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]

            # ── WORKOUT PHASE ────────────────────────────────
            if phase == "workout":
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                ts_ms = max(int(time.monotonic() * 1000) - start_ms, 1)
                result = landmarker.detect_for_video(mp_image, ts_ms)

                if result.pose_landmarks and len(result.pose_landmarks) > 0:
                    landmarks = result.pose_landmarks[0]
                    hip = extract_landmark_xy(landmarks, LEFT_HIP)
                    shoulder = extract_landmark_xy(landmarks, LEFT_SHOULDER)
                    wrist = extract_landmark_xy(landmarks, LEFT_WRIST)

                    raw_angle = compute_shoulder_angle(hip, shoulder, wrist)
                    smooth_angle = smoother.update(raw_angle)
                    state = sm.update(smooth_angle)
                    color = get_angle_color(smooth_angle)

                    hip_px = normalized_to_pixel(hip, w, h)
                    shoulder_px = normalized_to_pixel(shoulder, w, h)
                    wrist_px = normalized_to_pixel(wrist, w, h)

                    draw_arm_overlay(frame, hip_px, shoulder_px, wrist_px, color, smooth_angle)
                    draw_hud(frame, sm, smooth_angle, color, current_set, TOTAL_SETS)
                else:
                    draw_hud(frame, sm, smoother.value, COLOR_RED, current_set, TOTAL_SETS)
                    cv2.putText(frame, "No pose detected - face the camera",
                                (w // 2 - 220, h // 2), FONT, 0.8,
                                (100, 100, 255), 2, cv2.LINE_AA)

                # GIF
                if gif_player and gif_player.available:
                    draw_gif_panel(frame, gif_player.get_frame(), GIF_PANEL_WIDTH, GIF_PANEL_HEIGHT)
                else:
                    draw_no_gif_placeholder(frame, GIF_PANEL_WIDTH, GIF_PANEL_HEIGHT)

                # Set complete?
                if sm.reps >= REPS_PER_SET:
                    set_results.append({"reps": sm.reps, "peak_angle": sm.peak_angle})
                    print(f"[INFO] Set {current_set} complete! Reps: {sm.reps}, Peak: {sm.peak_angle:.1f}°")
                    if current_set >= TOTAL_SETS:
                        phase = "summary"
                    else:
                        phase = "cooldown"
                        cooldown_start = time.monotonic()

            # ── COOLDOWN PHASE ───────────────────────────────
            elif phase == "cooldown":
                elapsed = time.monotonic() - cooldown_start
                remaining = COOLDOWN_SECS - elapsed
                draw_cooldown_screen(frame, remaining, current_set, TOTAL_SETS)
                if remaining <= 0:
                    current_set += 1
                    sm.reset_for_new_set()
                    smoother.reset()
                    phase = "workout"
                    print(f"[INFO] Starting Set {current_set}...")

            # ── SUMMARY PHASE ────────────────────────────────
            elif phase == "summary":
                draw_summary_screen(frame, set_results, was_early_exit)

            cv2.imshow("Lateral Raises Tracker", frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                break

            if key in (ord("e"), ord("E")) and phase == "workout":
                set_results.append({"reps": sm.reps, "peak_angle": sm.peak_angle})
                print(f"[INFO] Set {current_set} exited early. Reps: {sm.reps}")
                was_early_exit = True
                if current_set >= TOTAL_SETS:
                    phase = "summary"
                else:
                    phase = "cooldown"
                    cooldown_start = time.monotonic()

            if phase == "summary" and key != 255:
                break

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user.")

    finally:
        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()

        elapsed = time.monotonic() - (start_ms / 1000)
        print("\n" + "=" * 55)
        print("  LATERAL RAISES — SESSION SUMMARY")
        print("=" * 55)
        total_reps = 0
        peak_angles = []
        for i, r in enumerate(set_results):
            reps = r["reps"]
            peak = r["peak_angle"]
            total_reps += reps
            if peak > 0.0:
                peak_angles.append(peak)
            peak_str = f"{peak:.1f}°" if peak > 0.0 else "—"
            print(f"  Set {i + 1}: {reps} reps  |  Peak Angle: {peak_str}")
        print(f"  {'─' * 40}")
        print(f"  Total Reps           : {total_reps}")
        if peak_angles:
            print(f"  Avg of Peak Angles   : {np.mean(peak_angles):.1f}°")
        print(f"  Session Duration     : {elapsed:.1f} seconds")
        if was_early_exit:
            print("  Note: Workout ended early by user.")
        print("=" * 55 + "\n")

        # Structured JSON output for API consumption
        import json
        result_json = {
            "exercise": "lateral_raises",
            "total_reps": total_reps,
            "avg_peak_angle": round(float(np.mean(peak_angles)), 1) if peak_angles else 0,
            "sets": set_results,
            "duration_secs": round(elapsed, 1),
            "early_exit": was_early_exit,
        }
        print(f"##RESULT_JSON##{json.dumps(result_json)}")


if __name__ == "__main__":
    main()
