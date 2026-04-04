"""
main1.py — Single entry point for the Rehab Pose Tracker.

Usage
-----
  python main1.py                              # web mode, opens browser
  python main1.py --port 8080                  # web mode, custom port
  python main1.py --cli                        # headless CLI
  python main1.py --cli --exercise arm_raise --stage 1
  python main1.py --list                       # print all exercises
"""

import argparse
import sys
import time
import webbrowser
import threading
import cv2

from logic.exercise_classifier import ExerciseClassifier, EXERCISES
from logic.rep_counter import RepCounter
from logic.session import SessionTracker
from logic.body_analyzer import BodyAnalyzer
from pose.pose_detector import PoseDetector


def run_cli(exercise: str = "arm_raise", stage: int = 0, camera: int = 0) -> None:
    cfg = EXERCISES[exercise]
    print(f"\nExercise : {cfg['display_name']}")
    print(f"Stage    : {cfg['stages'][stage]['label']}")
    print(f"Hold     : {cfg['hold_sec']}s per rep")
    print("Press Ctrl+C to stop.\n")

    detector    = PoseDetector()
    classifier  = ExerciseClassifier(exercise, stage=stage)
    rep_counter = RepCounter(hold_sec=cfg["hold_sec"])
    session     = SessionTracker(exercise, stage=stage)
    body_an     = BodyAnalyzer()

    cap = cv2.VideoCapture(camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera {camera}")
        sys.exit(1)

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue

            frame     = cv2.flip(frame, 1)
            mp_result = detector.detect(frame)

            if mp_result.pose_landmarks:
                lms     = mp_result.pose_landmarks[0]
                profile = body_an.update(lms, frame.shape)
                result  = classifier.classify(lms, frame.shape, profile)
            else:
                result  = {
                    "detected": False, "angle": None, "status": None,
                    "feedback": "No person detected", "strain_warning": False,
                }
                profile = body_an.profile

            strain    = result.get("strain_warning", False)
            rep_state = rep_counter.update(result.get("status") or "", strain)
            session.update(result["angle"], result["status"], rep_state)

            if result["detected"]:
                hold_bar = "#" * int(rep_state["hold_progress"] * 10)
                print(
                    f"  Angle: {str(result['angle']) + chr(176):<8} "
                    f"Status: {(result['status'] or ''):<10} "
                    f"Reps: {rep_state['reps']:<4} "
                    f"Hold: [{hold_bar:<10}] "
                    f"Peak: {session.get_summary()['peak_angle']}{chr(176)}"
                    + (" STRAIN" if strain else ""),
                    end="\r"
                )
            else:
                print(f"  {result['feedback']:<50}", end="\r")

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        log_path = session.save()
        s = session.get_summary()
        print(f"\n\n{'─'*48}")
        print(f"  Exercise     : {s['exercise']}  ({cfg['stages'][stage]['label']})")
        print(f"  Reps         : {s['total_reps']}")
        print(f"  Peak Angle   : {s['peak_angle']}{chr(176)}")
        print(f"  Avg Angle    : {s['average_angle']}{chr(176)}")
        print(f"  Accuracy     : {s['accuracy_pct']}%")
        print(f"  ROM Quality  : {s['rom_quality']}")
        print(f"  Strain Events: {s['strain_events']}")
        print(f"  Duration     : {s['duration_sec']}s")
        print(f"  Log saved    : {log_path}")
        print(f"{'─'*48}\n")


def run_web(host: str = "0.0.0.0", port: int = 8000) -> None:
    try:
        import uvicorn
    except ImportError:
        print("ERROR: uvicorn not found. Run: pip install uvicorn")
        sys.exit(1)
    from api.server import app

    url = f"http://localhost:{port}"
    print(f"\nRehab Pose Tracker — Web Mode")
    print(f"Server  : {url}")
    print(f"Press Ctrl+C to stop.\n")

    threading.Thread(
        target=lambda: (time.sleep(1.5), webbrowser.open(url)),
        daemon=True
    ).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")


def _parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rehab Pose Tracker")
    p.add_argument("--cli",      action="store_true", help="Headless CLI mode")
    p.add_argument("--exercise", default="arm_raise",
                   help=f"Exercise key. Choices: {list(EXERCISES.keys())}")
    p.add_argument("--stage",    type=int, default=0, help="Stage 0/1/2 (default: 0)")
    p.add_argument("--camera",   type=int, default=0, help="Camera index (default: 0)")
    p.add_argument("--port",     type=int, default=8000, help="Web server port")
    p.add_argument("--host",     default="0.0.0.0",     help="Web server host")
    p.add_argument("--list",     action="store_true",   help="List exercises and exit")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse()

    if args.list:
        print(f"\n{'Exercise':<25} {'Display Name':<28} Stages")
        print("─" * 70)
        for key, cfg in EXERCISES.items():
            stages = "  |  ".join(
                f"S{i+1}: {s['correct_min']}\xb0\u2013{s['correct_max']}\xb0"
                for i, s in enumerate(cfg["stages"])
            )
            print(f"  {key:<23} {cfg['display_name']:<28} {stages}")
        print()
        sys.exit(0)

    if args.exercise not in EXERCISES:
        print(f"Unknown exercise '{args.exercise}'. Run --list to see options.")
        sys.exit(1)

    max_stage = len(EXERCISES[args.exercise]["stages"]) - 1
    if args.stage > max_stage:
        print(f"Stage {args.stage} does not exist. Max: {max_stage}")
        sys.exit(1)

    if args.cli:
        run_cli(exercise=args.exercise, stage=args.stage, camera=args.camera)
    else:
        run_web(host=args.host, port=args.port)
