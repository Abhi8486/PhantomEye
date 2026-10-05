"""
Global Configuration & Toggles
"""
import os
from pathlib import Path

# --- Simple .env Parser ---
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

RTSP_USERNAME = os.getenv("RTSP_USERNAME", "")
RTSP_PASSWORD = os.getenv("RTSP_PASSWORD", "")
RTSP_IP = os.getenv("RTSP_IP", "camera-stream.local")


# ---------------------------------------------------------
# BACKGROUND DAEMON
# ---------------------------------------------------------
# Toggle to enable/disable the background daemon that processes all cameras simultaneously
ENABLE_BACKGROUND_DAEMON = False


# ---------------------------------------------------------
# TEST CAMERA MODES (CAM-031)
# ---------------------------------------------------------
TEST_CAMERA_ID = "CAM-031"

# 1. Video Testing Mode
ENABLE_TEST_CAMERA_VIDEO = True
TEST_VIDEO_PATH = "/run/media/abhishek/Data/Anronix/Intelligent Traffic Management/crime_tracking/153283-804933523_medium.mp4"

# 2. Frames Testing Mode
ENABLE_TEST_CAMERA_FRAMES = False
TEST_FRAMES_DIR = "/run/media/abhishek/Data/Anronix/Intelligent Traffic Management/crime_tracking/phantomeye_poc/data/test_frames"
