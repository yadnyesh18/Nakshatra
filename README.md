# 🌟 Nakshatra — AI-Powered Neuro-Rehabilitation System

> Real-time computer vision physiotherapy assistant with hybrid edge-cloud AI coaching.

Nakshatra uses your webcam to watch you perform rehabilitation exercises, measure joint angles frame-by-frame, count valid repetitions, detect strain events, and deliver AI-generated corrective coaching — all through a browser-based dashboard.

---

## 📋 Table of Contents

- [System Architecture](#-system-architecture)
- [Tech Stack](#-tech-stack)
- [File-by-File Breakdown](#-file-by-file-breakdown)
  - [Entry Points](#entry-points)
  - [API Layer](#api-layer)
  - [Logic Layer](#logic-layer)
  - [Pose Layer](#pose-layer)
  - [Frontend](#frontend)
  - [Configuration](#configuration)
- [Supported Exercises](#-supported-exercises)
- [AI Coaching Architecture](#-ai-coaching-architecture)
- [Setup & Running](#-setup--running)
- [Environment Variables](#-environment-variables)
- [API Reference](#-api-reference)
- [Session Data & Logs](#-session-data--logs)

---

## 🏗 System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser (frontend/)                       │
│  index.html — single-file dashboard with MJPEG stream + SSE     │
└────────────────────────────┬────────────────────────────────────┘
                             │  HTTP / SSE / MJPEG
┌────────────────────────────▼────────────────────────────────────┐
│                    FastAPI Server (backend/)                      │
│                                                                  │
│  app.py ──────► api/server.py (routes + camera worker thread)   │
│                      │                                           │
│          ┌───────────┼──────────────┐                           │
│          ▼           ▼              ▼                            │
│   pose/          logic/          logic/                          │
│   pose_detector  exercise_       rep_counter                     │
│   .py            classifier.py   .py                             │
│                      │                                           │
│                  logic/          logic/                          │
│                  body_analyzer   session.py                      │
│                  .py             (log → JSON)                    │
│                      │                                           │
│                  logic/llm_orchestrator.py                       │
│                  ┌──────────┬──────────────┐                    │
│                  ▼          ▼              ▼                     │
│              Gemini      Ollama/        Supabase                 │
│              Flash       Qwen2.5        pgvector                 │
│              (real-time) (clinical      (RAG/patient            │
│                           reports)       baselines)              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🛠 Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Web Server** | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) | Async HTTP/ASGI backend |
| **Streaming** | `sse-starlette` (SSE) + MJPEG over HTTP | Live metrics & video to browser |
| **Pose Detection** | [MediaPipe](https://developers.google.com/mediapipe) PoseLandmarker | 33-point skeleton tracking from webcam |
| **Computer Vision** | [OpenCV](https://opencv.org/) (`cv2`) | Frame capture, drawing overlays, JPEG encoding |
| **Numerics** | [NumPy](https://numpy.org/) | Angle math, deque smoothing, landmark coordinates |
| **Data Validation** | [Pydantic v2](https://docs.pydantic.dev/) | Request bodies + strict LLM output schemas |
| **LLM Orchestration** | [LangChain](https://www.langchain.com/) (LCEL chains) | Prompt templating, LLM routing, output parsing |
| **Real-time AI** | Google Gemini Flash (`langchain-google-genai`) | Sub-second coaching & cognitive evaluation |
| **Local/Private AI** | Ollama + Qwen 2.5 (`langchain-community`) | On-device clinical report generation |
| **RAG Memory** | [Supabase](https://supabase.com/) pgvector | Patient baseline embeddings & personalised retrieval |
| **Embeddings** | Google `embedding-001` (`langchain-google-genai`) | Vectorising patient calibration data |
| **Config** | `python-dotenv` | `.env` secret management |
| **Frontend** | Vanilla HTML + CSS + JavaScript | Single-file dashboard (no build step) |

---

## 📁 File-by-File Breakdown

### Entry Points

#### `backend/app.py`
The **application bootstrap**. Creates the root FastAPI instance, attaches CORS middleware (so the browser can talk to the server across origins), and mounts the API router from `api/server.py` under the `/api/v1` prefix. Also exposes a health-check `GET /` that returns `{"status": "online"}`. Run this file with Uvicorn to start the whole system.

Key responsibilities:
- CORS configuration (`allow_origins=["*"]` — restrict in production)
- Router mounting at `/api/v1`
- Uvicorn entry-point (`host="0.0.0.0", port=8000, reload=True`)

---

#### `backend/main.py`
An alternative single-process runner (development convenience script). Contains the same FastAPI app wiring as `app.py` but may include additional startup hooks or direct Uvicorn invocation without the modular router pattern. Use whichever matches your run command.

---

### API Layer

#### `backend/api/server.py`
The **core server — brain of the backend**. This ~385-line file orchestrates everything that happens during a live session.

**What it does:**

1. **Background camera worker thread** (`_camera_worker`): Runs in a separate `threading.Thread` so it never blocks the async FastAPI event loop. Each frame, it:
   - Reads from the webcam via `cv2.VideoCapture`
   - Calls `PoseDetector.detect()` to get 33 body landmarks
   - Calls `BodyAnalyzer.update()` to build/maintain a body profile
   - Calls `ExerciseClassifier.classify()` to measure the joint angle and determine `Correct / Partial / Rest / Warning`
   - Passes the status to `RepCounter.update()` which runs a state machine (`rest → moving → holding → complete`)
   - Passes everything to `SessionTracker.update()` for live metrics
   - Draws a HUD overlay (`_draw_overlay`) onto the frame: arm highlight in green/orange/red, angle badge, rep counter, hold progress bar, strain flash border
   - JPEG-encodes the annotated frame and places it in `_latest_jpeg`
   - Places the metrics dict in `_latest_data`
   - Both are shared via a `threading.Lock`

2. **HTTP Endpoints:**

   | Method | Path | Description |
   |--------|------|-------------|
   | `POST` | `/session/start` | Starts the camera worker for a chosen exercise + stage |
   | `POST` | `/session/stop`  | Stops the worker, saves session JSON, returns summary |
   | `GET`  | `/session/summary` | Returns live session metrics |
   | `GET`  | `/exercises` | Lists all exercise configs |
   | `GET`  | `/video_feed` | MJPEG stream (multipart) — displayed in browser `<img>` tag |
   | `GET`  | `/events` | Server-Sent Events stream — pushes JSON metrics every 100 ms |
   | `POST` | `/session/coach` | On-demand AI coaching call via Gemini |
   | `GET`  | `/` | Serves the frontend `index.html` with exercises injected as `window.__EXERCISES__` |

3. **`_SafeEncoder`**: Custom `json.JSONEncoder` subclass that converts NumPy scalars (`np.int64`, `np.float32`, `np.ndarray`) to native Python types, preventing JSON serialisation crashes.

4. **`_draw_overlay`**: Draws all visual HUD elements onto the OpenCV frame before it is JPEG-encoded — arm segments, joint dots, angle badges, threshold ranges, FPS counter, rep/accuracy HUD, hold progress bar, and strain warning border.

---

### Logic Layer

#### `backend/logic/exercise_classifier.py`
The **rehab exercise registry and posture judge**.

Contains `EXERCISES` — a dictionary that defines the full configuration for every supported exercise:
- Which 3 MediaPipe landmarks to measure (e.g. `right_shoulder → right_elbow → right_wrist`)
- Whether to invert the raw angle (e.g. for "raise" movements where 0° = arm down)
- Required hold duration in seconds
- Three progressive therapy stages, each with `correct_min`, `correct_max`, and a `partial_range`

`ExerciseClassifier` class:
- On each frame, extracts the 3 landmark pixel positions and calls `calculate_angle()`
- Smooths the raw angle with a 7-frame moving average (`AngleSmoother`)
- Applies a `body_profile.angle_offset` correction (from `BodyAnalyzer`) to personalise thresholds for broad/narrow shoulders and long/short arms
- Detects **strain events** — a sudden angle drop of more than 20° in one frame, indicating pain-guarding
- Returns a result dict containing: `status`, `feedback`, `angle`, `threshold_min/max`, `arm_points`, `strain_warning`, `stage_label`

---

#### `backend/logic/angle.py`
A small but critical **trigonometry utility module**.

- `calculate_angle(a, b, c)`: Computes the interior angle in degrees at vertex `b` (elbow) formed by the vectors `b→a` (toward shoulder) and `b→c` (toward wrist). Uses dot product / arccosine, clamped to `[0°, 180°]`.
- `AngleSmoother`: A `deque`-based moving-average filter with configurable window size. Applied to every angle stream to reduce MediaPipe jitter without introducing perceptible lag.

---

#### `backend/logic/rep_counter.py`
A **finite state machine for physiotherapy-aware repetition counting**.

Standard fitness rep counters just count up/down crossings. This one is different — rehab patients must *hold* the correct position for a configurable duration (`hold_sec`) before a rep is counted.

States: `rest → moving → holding → complete → rest`

- **rest**: patient at or below partial range; waits for movement
- **moving**: patient in partial zone, approaching target; 5-frame debounce before transitioning
- **holding**: patient in correct zone; accumulates `hold_elapsed`; only counts rep when `hold_elapsed ≥ hold_sec`
- **complete**: rep counted; waits for patient to return to rest before accepting next rep

Strain events immediately reset the hold and return the patient to `rest`.

Returns a `dict` with `reps`, `hold_progress` (0.0–1.0 for the progress bar), `state`, and `strain_events` count.

---

#### `backend/logic/session.py`
The **session recorder and physiotherapy progress reporter**.

Accumulates per-frame data throughout a session and, on `save()`, writes a structured JSON file to `backend/logs/`.

Tracks:
- All angles seen (to compute `average_angle` and `peak_angle`)
- Frames spent in each status zone (`Correct`, `Partial`, `Rest`, `Warning`, `Incorrect`) — used for accuracy % and ROM quality rating
- Total reps and strain events (sourced from `RepCounter`)
- Session duration

`get_summary()` returns a standardised metrics dict used by both the SSE stream (live HUD) and the `/session/stop` API response.

`_generate_note()` produces a plain-English rehab progress note (e.g. *"Good ROM achieved — consider advancing to next stage."*) embedded in the saved JSON for clinician review.

Log filenames follow the pattern: `{exercise}_stage{N}_{YYYYMMDD_HHMMSS}.json`

---

#### `backend/logic/body_analyzer.py`
An **adaptive body profiling engine** — the personalisation engine.

Over the first 30 frames of a session, it accumulates normalised measurements from MediaPipe landmarks:
- Shoulder width (relative to torso height)
- Hip width
- Upper arm length
- Forearm length
- Torso height

After calibration locks (`_lock_profile`):
- Classifies the patient as `broad / average / narrow` shoulders and `long / average / short` arms
- Computes an `angle_offset` (e.g. −8° for broad shoulders who appear to have a wider ROM than they do)
- Detects **pain-guarding**: if the arm rests elevated, `rom_offset` is negative to lower the exercise thresholds
- Computes adaptive rendering parameters (`joint_radius`, `bone_thickness`, `active_thickness`) scaled to the patient's apparent size in frame

The resulting `BodyProfile` dataclass is passed to both `ExerciseClassifier` (threshold adjustment) and `PoseDetector.draw_skeleton()` (rendering).

---

#### `backend/logic/llm_orchestrator.py`
The **hybrid edge-cloud AI orchestration layer** — the most architecturally complex file in the project.

Implements three distinct AI routes, all using LangChain LCEL (pipe-syntax) chains:

**Route 1 — Real-time Physical Feedback (Gemini Flash)**
- For every set of reps, retrieves the patient's calibration baseline from Supabase pgvector (RAG step)
- Injects it into the `_PHYSICAL_FEEDBACK_PROMPT` PromptTemplate
- Calls Gemini Flash with `temperature=0.25` (factual, consistent medical cues)
- Parses and validates the JSON response against the `PhysicalFeedbackOutput` Pydantic model
- Returns: `{message: str, alert: bool, delta_pct: float}`
- Hardcoded fallback response ensures the demo never crashes

**Route 2 — Cognitive Memory Evaluation (Gemini Flash)**
- Receives a list of target words and the patient's transcribed verbal response (from a speech-to-text step)
- Scores recall accuracy (phonetic matching allowed) out of 100
- Suggests difficulty escalation if score > 85%
- Returns: `{score, words_recalled, feedback, difficulty_up}`

**Route 3 — Clinical Report Generation (Local Ollama/Qwen2.5)**
- Called at end-of-day with the full session log JSON
- Routes to the **local** Qwen 2.5 model running on an Ollama server (privacy-first; no patient data leaves the network)
- Generates a full clinical narrative for the treating physician
- Validates output against `ClinicalReportOutput` Pydantic model
- Returns: `{patient_session_id, overall_score, physical_summary, cognitive_summary, recommendations[], red_flags[]}`

**Memory Layer (Supabase pgvector)**
- `store_patient_baseline()`: Converts calibration data to a natural-language string, embeds it with Google `embedding-001`, upserts into the `patient_baselines` table
- `_retrieve_patient_baseline()`: Fetches the baseline JSON for a given `patient_id` for RAG injection

All three AI components initialise as singletons at import time, with graceful degradation — if a model is unavailable, the hardcoded fallback is returned instead of raising an exception.

---

### Pose Layer

#### `backend/pose/pose_detector.py`
The **MediaPipe PoseLandmarker wrapper**.

- Initialises MediaPipe `PoseLandmarker` in `VIDEO` running mode with confidence thresholds of 0.6 for detection, presence, and tracking. Loads the `.task` model file from `backend/models/pose_landmarker.task`.
- `detect(frame)`: Converts BGR→RGB, wraps in `mp.Image`, calls `detect_for_video()` with a monotonically increasing timestamp. Returns a `PoseLandmarkerResult` with up to 1 detected pose.
- `draw_skeleton()`: Renders all 33 landmark connections colour-coded by body region (face=grey, left arm=blue, right arm=green, legs=purple/gold). Active joints (those involved in the current exercise) are highlighted in white/yellow and drawn thicker. Also renders the calibration progress bar during the first 30 frames.
- `get_landmark_px()`: Converts a named landmark (e.g. `"right_elbow"`) to pixel coordinates `[x, y]`, returning `None` if the landmark is occluded (visibility < 0.35).

---

### Frontend

#### `frontend/index.html`
A **single-file, zero-dependency web dashboard** (~35 KB of HTML/CSS/JS).

What it does:
- Displays the live webcam feed as an MJPEG stream in an `<img>` tag (pointing to `/video_feed`)
- Opens an `EventSource` connection to `/events` and updates the dashboard in real time:
  - Current angle, status badge (Correct/Partial/Rest/Warning), rep count
  - Accuracy %, peak angle, hold progress, strain event count
  - Body calibration info (shoulder type, limb type, angle offset)
- Exercise selector populated from `window.__EXERCISES__` (injected server-side by `GET /`)
- Stage selector (1, 2, 3) with live switching
- Start / Stop session buttons that call `POST /session/start` and `POST /session/stop`
- "Get AI Coaching" button that calls `POST /session/coach` and displays Gemini's corrective message
- Responsive layout, no npm, no bundler — pure browser APIs

---

### Configuration

#### `backend/.env`
Runtime secrets (not committed). Copy from `.env.example` and fill in:

```
GOOGLE_API_KEY=...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
OLLAMA_HOST_IP=...      # IP of the machine running Ollama
OLLAMA_PORT=11434
OLLAMA_MODEL=qwen2.5
GEMINI_MODEL=gemini-3.1-flash-lite-preview
```

#### `backend/.env.example`
Template showing required environment variable names without secret values.

#### `requirements.txt`
All Python dependencies. Install with `pip install -r requirements.txt`.

#### `pyrightconfig.json`
Pyright type-checker configuration (sets `pythonVersion`, `venvPath`, etc.). Does not affect runtime.

---

## 🤸 Supported Exercises

| Key | Display Name | Joint Measured | Stages |
|-----|-------------|----------------|--------|
| `arm_raise` | Assisted Arm Raise | Shoulder–Elbow–Wrist (elevation) | Low / Mid / High |
| `pendulum_swing` | Pendulum Swing | Shoulder–Elbow–Wrist (swing) | Minimal / Moderate / Full |
| `shoulder_abduction` | Side Arm Lift | Hip–Shoulder–Elbow (abduction) | Low / Mid / Full |
| `shoulder_rotation` | Shoulder External Rotation | Shoulder–Elbow–Wrist (rotation) | Minimal / Moderate / Full |
| `elbow_flexion` | Elbow Bend | Shoulder–Elbow–Wrist (flexion) | Minimal / Moderate / Full |
| `elbow_extension` | Elbow Straighten | Shoulder–Elbow–Wrist (extension) | Minimal / Moderate / Full |

Each exercise has 3 progressive stages with increasingly demanding angle thresholds — patients progress through them as their range of motion improves.

---

## 🤖 AI Coaching Architecture

```
Live Session (every N reps)
         │
         ▼
POST /session/coach
         │
         ▼
logic/llm_orchestrator.py
         │
         ├── 1. Retrieve patient baseline ──► Supabase pgvector (RAG)
         │
         ├── 2. Build prompt ──────────────► PromptTemplate + baseline context
         │
         └── 3. Route to model
                  │
                  ├── Real-time coaching ──► Google Gemini Flash
                  │                         (< 500 ms target latency)
                  │
                  └── Clinical report ────► Local Ollama / Qwen 2.5
                                            (private, on-device)
```

All AI responses are validated against strict Pydantic schemas before being returned. If validation fails or the model is unreachable, a hardcoded fallback response is returned so the session continues without interruption.

---

## 🚀 Setup & Running

### Prerequisites
- Python 3.11+
- Webcam
- (Optional) Ollama running locally or on a networked machine with `qwen2.5` pulled
- (Optional) Supabase project with a `patient_baselines` table and pgvector enabled

### Install

```bash
git clone <repo-url>
cd Nakshatra/backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r ../requirements.txt
```

### Download MediaPipe Model

Download the pose landmarker model and place it at:
```
backend/models/pose_landmarker.task
```
Download from: https://developers.google.com/mediapipe/solutions/vision/pose_landmarker

### Configure Environment

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

### Run

```bash
cd backend
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser at: **http://localhost:8000**

---

## 🔑 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Yes (for Gemini) | Google AI Studio API key |
| `SUPABASE_URL` | No | Supabase project URL for RAG personalisation |
| `SUPABASE_SERVICE_ROLE_KEY` | No | Supabase service role key |
| `OLLAMA_HOST_IP` | No | IP of the machine running Ollama |
| `OLLAMA_PORT` | No | Ollama port (default: `11434`) |
| `OLLAMA_MODEL` | No | Local model name (default: `qwen2.5`) |
| `GEMINI_MODEL` | No | Gemini model name (default: `gemini-3.1-flash-lite-preview`) |

> The system degrades gracefully — if Gemini or Ollama is unavailable, hardcoded fallback responses are returned and the session continues normally.

---

## 📡 API Reference

| Method | Endpoint | Body | Returns |
|--------|----------|------|---------|
| `GET` | `/` | — | HTML dashboard |
| `GET` | `/video_feed` | — | MJPEG stream |
| `GET` | `/events` | — | SSE stream (JSON metrics every 100 ms) |
| `GET` | `/exercises` | — | All exercise definitions |
| `POST` | `/session/start` | `{exercise, camera, stage}` | Session config |
| `POST` | `/session/stop` | — | Session summary + log path |
| `GET` | `/session/summary` | — | Live session metrics |
| `POST` | `/session/coach` | `{exercise, reps, avg_angle, strain_events}` | AI coaching message |

---

## 💾 Session Data & Logs

Session logs are saved in `backend/logs/` as JSON files:

```json
{
  "exercise": "arm_raise",
  "stage": 1,
  "total_reps": 8,
  "peak_angle": 74.3,
  "average_angle": 52.1,
  "accuracy_pct": 61.5,
  "rom_quality": "Good",
  "strain_events": 1,
  "duration_sec": 142.3,
  "frames_tracked": 4269,
  "zone_breakdown": { "Correct": 38.2, "Partial": 24.1, "Rest": 35.1, "Warning": 2.6 },
  "timestamp": "2025-04-04T14:32:11.221Z",
  "progress_note": "Good ROM achieved — consider advancing to next stage. Consistent performance — patient is progressing well."
}
```

These logs can be fed directly into `generate_session_report()` for an AI-generated clinical summary via the local Ollama model.

---

## 📂 Project Structure

```
Nakshatra/
├── requirements.txt              # Python dependencies
├── pyrightconfig.json            # Type checker config
├── frontend/
│   └── index.html               # Single-file web dashboard
└── backend/
    ├── app.py                   # FastAPI root app + CORS + router mount
    ├── main.py                  # Alternate entry point / dev runner
    ├── .env                     # Secrets (not committed)
    ├── .env.example             # Secret template
    ├── models/
    │   └── pose_landmarker.task # MediaPipe model file (download separately)
    ├── logs/                    # Auto-created session JSON logs
    ├── api/
    │   └── server.py            # All routes, camera worker, video/SSE streams
    ├── pose/
    │   └── pose_detector.py     # MediaPipe PoseLandmarker wrapper
    └── logic/
        ├── angle.py             # Angle calculation + moving-average smoother
        ├── body_analyzer.py     # Body proportions calibration → BodyProfile
        ├── exercise_classifier.py # Exercise registry + per-frame posture judge
        ├── rep_counter.py       # Rehab-aware rep counting state machine
        ├── session.py           # Session metrics recorder + JSON log writer
        └── llm_orchestrator.py  # Gemini + Ollama + Supabase RAG orchestration
```
