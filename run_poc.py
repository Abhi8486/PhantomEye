"""
PhantomEye Master 1-Click Launcher
Starts FastAPI + WebSocket Backend, Serves GIS Tactical Frontend, and Runs AI Background Pipeline.
"""

import uvicorn
import webbrowser
import threading
import time
import os
# Fix for FFmpeg libavcodec async_lock crash during multithreaded stream decoding
os.environ["OPENCV_FFMPEG_THREADS"] = "1"
import sys
from pathlib import Path

# Configure UTF-8 for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from backend.config import ENABLE_BACKGROUND_DAEMON

def open_browser():
    time.sleep(1.5)
    print("\n[+] Opening PhantomEye Tactical GIS Command Dashboard in Browser...")
    try:
        webbrowser.open("http://localhost:8000")
    except Exception:
        pass


def main():
    print("=" * 70)
    print("  [*] PHANTOMEYE - STATEWIDE CCTV AI SURVEILLANCE COMMAND PLATFORM")
    print("  [+] Version          : 1.0.0 (Hackathon Working POC)")
    print("  [+] Dashboard URL    : http://localhost:8000")
    print("  [+] Target Scale     : 50 Logical Cameras -> 80,000 Statewide Cameras")
    print("  [+] Federation       : 26 Gujarat Government Departments (Home, RTO, ICCC...)")
    print("=" * 70)

    # Launch browser automatically
    threading.Thread(target=open_browser, daemon=True).start()

    # Start Background Ingestion Pipeline
    if ENABLE_BACKGROUND_DAEMON:
        try:
            from core_ai.background_ingester import ingester_daemon
            ingester_daemon.start()
        except Exception as e:
            print(f"[!] Failed to start background ingester: {e}")
    else:
        print("[*] Background Ingester Daemon is DISABLED. To enable, set ENABLE_BACKGROUND_DAEMON = True in run_poc.py")

    # Start FastAPI Uvicorn Server
    try:
        uvicorn.run(
            "backend.app:app",
            host="0.0.0.0",
            port=8000,
            reload=False,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n[*] Shutting down PhantomEye server...")
    finally:
        if ENABLE_BACKGROUND_DAEMON:
            try:
                from core_ai.background_ingester import ingester_daemon
                ingester_daemon.stop()
            except Exception:
                pass
        print("[*] Shutdown complete. Goodbye.")


if __name__ == "__main__":
    main()
