"""
main.py
Unified entry point for the rehabilitation pose tracking system.

Modes:
    GUI  (default) : live webcam window with overlays
    CLI  (--cli)   : headless terminal output, no window

Usage:
    python main.py                          # GUI, arm_raise
    python main.py --exercise elbow_flexion # GUI, different exercise
    python main.py --cli                    # headless terminal mode
    python main.py --list                   # print available exercises

Press 'q' (GUI) or Ctrl+C (CLI) to stop and save session log.
"""

import argparse
import sys
import time
import cv2

from pose.pose_detector import PoseDetector
from logic.exercise_classifier import ExerciseClassifier, EXERCISES
from logic.rep_counter import RepCounter
from logic.session import SessionTracker

# ── Display constants ─────────────────────────────────────────────────────────
FONT      = cv2.FONT_HERSHEY_SIMPLEX
GREEN     = (0, 200, 0)
ORANGE    = (0, 165, 255)
RED       = (0, 0, 220)
YELLOW    = (0, 220, 220)
WHITE     = (255, 255, 255)
ARM_COLOR = (255, 140, 0)

STATUS_COLOR = {"Correct": GREEN, "Partial": ORANGE, "Incorrect": RED}


# ── Overlay rendering ─────────────────────────────────────────────────────────

def _draw_overlay(frame, result: dict, reps: int, fps: float, summary: dict) -> None:
    """Render all HUD elements onto frame in-place."""
    h, w = frame.shape[:2]

    # Arm highlight
    if result["detected"] and len(result["arm_points"]) == 3:
        pts = result["arm_points"]
        for i in range(len(pts) - 1):
            cv2.line(frame, pts[i], pts[i + 1], ARM_COLOR, 4, cv2.LINE_AA)
        for pt in pts:
            cv2.circle(frame, pt, 9, ARM_COLOR, -1, cv2.LINE_AA)

    # Angle badge near middle joint (elbow)
    if result["detected"] and result["angle"] is not None:
        mid = result["arm_points"][1]
        cv2.putText(frame, f"{result['angle']}\xb0",
                    (mid[0] + 14, mid[1] - 14), FONT, 0.85, WHITE, 2, cv2.LINE_AA)

    # Status banner (bottom strip)
    color = STATUS_COLOR.get(result.get("status", ""), RED)
    cv2.rectangle(frame, (0, h - 55), (w, h), (20, 20, 20), -1)
    cv2.putText(frame, result.get("feedback", ""), (14, h - 18),
                FONT, 0.8, color, 2, cv2.LINE_AA)

    # Top-left HUD: FPS + exercise name
    cv2.putText(frame, f"FPS: {fps:.1f}", (14, 32), FONT, 0.65, YELLOW, 2, cv2.LINE_AA)
    ex_label = EXERCISES.get(result.get("exercise_name", ""), {}).get("display_name", "")
    cv2.putText(frame, ex_label, (14, 60), FONT, 0.65, WHITE, 2, cv2.LINE_AA)

    # Top-right HUD: reps + accuracy
    reps_txt = f"Reps: {reps}"
    acc_txt  = f"Acc: {summary.get('accuracy_pct', 0.0):.1f}%"
    cv2.putText(frame, reps_txt, (w - 160, 32), FONT, 0.65, GREEN,  2, cv2.LINE_AA)
    cv2.putText(frame, acc_txt,  (w - 160, 60), FONT, 0.65, YELLOW, 2, cv2.LINE_AA)


# ── Main loop ─────────────────────────────────────────────────────────────────

def run(exercise: str = "arm_raise", cli_mode: bool = False,
        camera_index: int = 0) -> None:
    """
    Main webcam loop.

    Args:
        exercise:     exercise key from EXERCISES registry.
        cli_mode:     if True, skip cv2.imshow and print to terminal.
        camera_index: OpenCV camera device index.
    """
    detector    = PoseDetector()
    classifier  = ExerciseClassifier(exercise)
    rep_counter = RepCounter()
    session     = SessionTracker(exercise)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {camera_index}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    prev_time = time.time()
    print(f"Exercise: {EXERCISES[exercise]['display_name']}")
    print("Press 'q' (GUI) or Ctrl+C (CLI) to stop.\n")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue

            frame = cv2.flip(frame, 1)

            # ── Inference ────────────────────────────────────────────────────
            mp_result = detector.detect(frame)

            if mp_result.pose_landmarks:
                detector.draw_skeleton(frame, mp_result.pose_landmarks[0])
                result = classifier.classify(mp_result.pose_landmarks[0], frame.shape)
            else:
                result = {"detected": False, "angle": None, "status": None,
                          "feedback": "No person detected", "arm_points": [],
                          "exercise_name": exercise}

            # ── Rep counting + session update ─────────────────────────────────
            reps = rep_counter.update(result.get("status") or "")
            session.update(result["angle"], result["status"], reps)
            summary = session.get_summary()

            # ── FPS ───────────────────────────────────────────────────────────
            now = time.time()
            fps = 1.0 / max(now - prev_time, 1e-6)
            prev_time = now

            # ── Output ────────────────────────────────────────────────────────
            if cli_mode:
                if result["detected"]:
                    print(
                        f"Angle: {result['angle']}\xb0  "
                        f"Status: {result['status']:<10}  "
                        f"Reps: {reps}  "
                        f"Acc: {summary['accuracy_pct']:.1f}%  "
                        f"FPS: {fps:.1f}",
                        end="\r"
                    )
            else:
                _draw_overlay(frame, result, reps, fps, summary)
                cv2.imshow("Rehabilitation Pose Tracker", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if not cli_mode:
            cv2.destroyAllWindows()

        log_path = session.save()
        final = session.get_summary()
        print(f"\n\n── Session Summary ──────────────────────────")
        print(f"  Exercise  : {final['exercise']}")
        print(f"  Reps      : {final['total_reps']}")
        print(f"  Avg Angle : {final['average_angle']}\xb0")
        print(f"  Accuracy  : {final['accuracy_pct']}%")
        print(f"  Duration  : {final['duration_sec']}s")
        print(f"  Log saved : {log_path}")


# ── CLI argument parsing ──────────────────────────────────────────────────────

def _parse_args():
    parser = argparse.ArgumentParser(description="Rehabilitation Pose Tracker")
    parser.add_argument(
        "--exercise", default="arm_raise",
        help=f"Exercise to track. Choices: {list(EXERCISES.keys())}"
    )
    parser.add_argument(
        "--cli", action="store_true",
        help="Run in headless CLI mode (no window)"
    )
    parser.add_argument(
        "--camera", type=int, default=0,
        help="Camera device index (default: 0)"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List available exercises and exit"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.list:
        print("Available exercises:")
        for key, cfg in EXERCISES.items():
            print(f"  {key:<25} → {cfg['display_name']}  "
                  f"(correct: {cfg['correct_min']}°–{cfg['correct_max']}°)")
        sys.exit(0)

    if args.exercise not in EXERCISES:
        print(f"Unknown exercise '{args.exercise}'. Run with --list to see options.")
        sys.exit(1)

    run(exercise=args.exercise, cli_mode=args.cli, camera_index=args.camera)
