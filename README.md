# 👁️ PHANTOMEYE — State-Level CCTV AI Surveillance & GIS Command Center (POC v1.0)

> **Official Gujarat Statewide CCTV Hackathon Working Prototype & Reference Implementation**  
> Scalable Architecture: 50 Onboarded Logical Cameras $\rightarrow$ 80,000 Statewide Cameras Across 26 Government Departments.

---

## 🏛️ 1. Architecture Highlights

```
                          ┌───────────────────────────┐
                          │   50 GUJARAT CCTV CAMERAS │
                          │  (26 Departments Seeded)  │
                          └─────────────┬─────────────┘
                                        │
                          ┌─────────────▼─────────────┐
                          │   VMS FEDERATION LAYER    │
                          │ • Police CSITMS (VMS-A)   │
                          │ • Smart City ICCC (VMS-B) │
                          │ • Direct RTSP / ONVIF     │
                          └─────────────┬─────────────┘
                                        │
                          ┌─────────────▼─────────────┐
                          │     AI ENGINE (EDGE)      │
                          │ • YOLOv8s (9.0ms GPU)     │
                          │ • ZeroTrailTracker        │
                          │ • ANPR + VAHAN / eGujCop  │
                          │ • Florence-2 Scene VLM    │
                          └─────────────┬─────────────┘
                                        │ JSON Metadata (<500 Mbps WAN)
                          ┌─────────────▼─────────────┐
                          │  FASTAPI + SQLITE SPATIAL │
                          │   Central CCTV Registry   │
                          └─────────────┬─────────────┘
                                        │ REST + WebSocket
                          ┌─────────────▼─────────────┐
                          │  TACTICAL GIS COMMAND UI  │
                          │ • Leaflet Map & FOV Cones │
                          │ • Animated Route Replay   │
                          │ • Real-time Watchlist     │
                          │ • VMS Health & Analytics  │
                          └───────────────────────────┘
```

---

## 🚀 2. Quick Start (1-Click Run)

To launch the full system (FastAPI backend + WebSocket stream + Leaflet Tactical Frontend):

```bash
# Navigate to the POC directory
cd phantomeye_poc

# Install the exact dependencies required for this project
pip install -r requirements.txt

# Configure your secure RTSP credentials
# Create a .env file in the root directory (or edit the existing one) and add:
# RTSP_USERNAME=your_username
# RTSP_PASSWORD=your_password

# Launch 1-Click Master Application
python run_poc.py
```

* **Dashboard URL:** `http://localhost:8000` (Opens automatically in your browser).
* **API Documentation:** `http://localhost:8000/docs` (Interactive Swagger UI).

### Stopping the Server
To gracefully stop the server, go to the terminal where `run_poc.py` is running and press:
```powershell
Ctrl + C
```
The server will safely release all camera resources and terminate background processes.

---

## ⚙️ 3. Configuration & Toggles

### Background Daemon Toggle
By default, analyzing all connected cameras simultaneously is incredibly resource-intensive. To allow you to focus on developing and testing single cameras without overloading your GPU, a toggle is provided inside `backend/config.py`.

In `backend/config.py`:
```python
# Toggle to enable/disable the background daemon that processes all cameras simultaneously
ENABLE_BACKGROUND_DAEMON = False
```
* **When `False` (Default)**: The background daemon will not start. The AI will **only process the specific camera** you are actively watching in the Live Surveillance frontend. 
* **When `True`**: The AI will actively run on **every single active camera** in the database in the background, logging vehicles and plates autonomously. 

### Debug Frames Toggle
If you need to inspect what the OCR engine is looking at, you can save the best frame and license plate crops to your disk.

In `core_ai/anpr.py`:
```python
# Set to True to save vehicle and plate crops to data/best-frames/ and data/plate_crops/
SAVE_DEBUG_FRAMES = False
```
* **When `True`**: Every processed license plate will save crop images into `data/best-frames/` and `data/plate_crops/`. *(Warning: This can quickly consume disk space if the Background Daemon is also running!)*

### Test Camera Toggles (CAM-031)
We have a dedicated test camera setup assigned to `CAM-031` allowing you to inject arbitrary test sources without breaking live tracking for production cameras (e.g., `CAM-004`).

In `backend/config.py`:
```python
# 1. Video Testing Mode
ENABLE_TEST_CAMERA_VIDEO = False
TEST_VIDEO_PATH = "/path/to/your/video.mp4"

# 2. Frames Testing Mode
ENABLE_TEST_CAMERA_FRAMES = False
TEST_FRAMES_DIR = "/path/to/your/frames/folder"
```
* **Video Mode**: Replaces `CAM-031`'s live RTSP feed with the specified local MP4 file.
* **Frames Mode**: Replaces `CAM-031`'s feed with a folder containing individual frames (e.g., `.jpg` or `.png`). The frames are played sequentially in a loop, simulating a video feed. This is excellent for testing edge cases, specific OCR crops, and frame-by-frame regressions.

*(Note: You must restart `run_poc.py` for any toggle changes to take effect.)*

---

## 🧠 4. AI Pipeline Architecture

PhantomEye utilizes a dual-pipeline architecture to balance between high-performance real-time viewing and massive statewide background ingestion.

### A. The Live Stream Processor (`video_stream.py`)
**Purpose:** Provides a high-framerate, zero-delay MJPEG video stream with real-time bounding boxes directly to the user's dashboard.
* **Scope:** Runs **only** on the single camera currently being viewed by the user. 
* **Flow:**
  1. User requests a camera feed via the frontend UI.
  2. The backend instantly kills any other active Live Stream Processors to free up GPU resources.
  3. The video stream is decoded (via RTSP or local fallback MP4).
  4. **Detector & Tracker:** YOLO runs on every frame to draw bounding boxes, and ZeroTrail tracks vehicles across frames.
  5. **OCR Queue:** When a vehicle enters the designated ROI, the best frames are pushed to a bounded queue.
  6. **Worker Thread:** A persistent OCR worker picks up frames from the queue, runs ANPR (via EasyOCR + VLM fallback), uses Multi-Frame Fusion to build consensus, and broadcasts the confirmed plate back to the UI via WebSockets.

### B. The Background Ingester Daemon (`core_ai/background_ingester.py`)
**Purpose:** Continuously monitors all active cameras statewide, running at a lower frame rate to detect wanted vehicles and log traffic data anonymously in the background without needing a user to watch.
* **Scope:** Runs on **all active cameras** listed in the database.
* **Flow:**
  1. The daemon polls the database for active cameras.
  2. Uses a highly constrained `ThreadPoolExecutor` (e.g., 4 workers) to process the cameras round-robin style, ensuring the CPU/GPU isn't locked up.
  3. **Detector & Tracker:** Fetches a frame (~1-2 FPS per camera) using a shared lightweight pipeline and tracks vehicles.
  4. **Color & Event Logging:** Logs basic vehicle events and extracts colors.
  5. **Background OCR:** If the track yields a high-confidence crop, it is sent to the shared ANPR Engine.
  6. **Multi-Frame Fusion & DB Insert:** Validated plates are cross-referenced with the VAHAN database and permanently written to the `vehicle_anpr` database so they can be queried later in the universal search.
