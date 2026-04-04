# Rehab Pose Tracker

AI-powered physiotherapy exercise assistant using MediaPipe Pose.
Tracks joint angles in real time and guides patients through recovery exercises.

## Project Structure

```
nakshatra_project/
├── backend/                  ← Python server + AI logic
│   ├── api/
│   │   └── server.py         ← FastAPI: video stream, SSE, REST endpoints
│   ├── logic/
│   │   ├── angle.py          ← Angle calculation + smoothing
│   │   ├── body_analyzer.py  ← Body shape calibration + ROM detection
│   │   ├── exercise_classifier.py  ← Rehab exercise registry + classifier
│   │   ├── rep_counter.py    ← Hold-timer rep counter + strain detection
│   │   └── session.py        ← Session tracking + progress report
│   ├── pose/
│   │   └── pose_detector.py  ← MediaPipe PoseLandmarker wrapper
│   ├── models/               ← MediaPipe .task model file (not in git)
│   ├── logs/                 ← Session JSON reports (not in git)
│   └── main.py               ← Single entry point (web + CLI modes)
├── frontend/
│   └── index.html            ← Web dashboard (single file, no build step)
├── requirements.txt
└── .gitignore
```

## Setup

```bash
# 1. Create virtual environment with Python 3.12
python3.12 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download MediaPipe model
curl -L -o backend/models/pose_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task
```

## Run

```bash
# Web mode — starts server and opens browser automatically
python backend/main.py

# Custom port
python backend/main.py --port 8080

# Headless CLI mode
python backend/main.py --cli

# CLI with specific exercise and stage
python backend/main.py --cli --exercise elbow_flexion --stage 1

# List all exercises
python backend/main.py --list
```

## Exercises

| Key | Name | Stages |
|-----|------|--------|
| `pendulum_swing` | Pendulum Swing | S1: 5–20° / S2: 20–40° / S3: 40–70° |
| `arm_raise` | Assisted Arm Raise | S1: 15–40° / S2: 40–80° / S3: 80–130° |
| `shoulder_abduction` | Side Arm Lift | S1: 10–30° / S2: 30–70° / S3: 70–120° |
| `shoulder_rotation` | Shoulder External Rotation | S1–S3 |
| `elbow_flexion` | Elbow Bend | S1–S3 |
| `elbow_extension` | Elbow Straighten | S1–S3 |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web dashboard |
| `GET` | `/video_feed` | MJPEG live video stream |
| `GET` | `/events` | SSE live metrics (angle, reps, status) |
| `POST` | `/session/start` | Start session `{exercise, stage, camera}` |
| `POST` | `/session/stop` | Stop and save session |
| `GET` | `/session/summary` | Current session metrics |
| `GET` | `/exercises` | List all exercises |
