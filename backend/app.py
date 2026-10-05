"""
PhantomEye Master FastAPI Application
Serves Central CCTV Registry, ANPR & VAHAN Intelligence,
Cross-Camera Trajectory Engine, VMS Federation, and Interactive GIS Frontend.
"""

import os
import asyncio
import json
import random
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, WebSocket, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, APIKeyQuery
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from .database.schema import init_db, get_db_connection
from .database.seed_data import seed_database
from .routers import (
    cameras,
    events,
    vehicles,
    tracking,
    vms,
    alerts,
    analytics,
    video_stream,
    ai_copilot,
    search_upload,
    tactical_ops,
    anomaly_events,
    review,
    ingest
)
from .routers.alerts import alert_manager

POC_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = POC_DIR / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure DB is initialized
    init_db()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as count FROM cameras;")
    count = c.fetchone()["count"]
    conn.close()

    if count < 30:
        seed_database()

    try:
        yield
    finally:
        # Shutdown: Stop all background video streams and OCR workers
        try:
            for cam_id, manager in list(video_stream.active_captures.items()):
                print(f"[*] Stopping video stream manager for {cam_id}...")
                try:
                    manager.release()
                except Exception as e:
                    print(f"Error releasing {cam_id}: {e}")
        except Exception as e:
            print(f"Shutdown error: {e}")
            
        print("[*] Red EYE Surveillance Backend Shutdown Complete.")


# ─────────────────────────────────────────────────────────────
# FASTAPI APP INSTANCE
# ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="Red EYE - Gujarat Unified AI CCTV Surveillance Command System",
    description="Unified Central CCTV Registry, Real-Time ANPR, Cross-Camera Trajectory, and Multi-Vendor VMS Federation with Florence-2 & Gemini Multimodal Intelligence.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import Request, WebSocket

async def verify_api_key(request: Request = None, websocket: WebSocket = None):
    # Safely extract from either Request or WebSocket
    headers = request.headers if request else (websocket.headers if websocket else {})
    query_params = request.query_params if request else (websocket.query_params if websocket else {})
    
    key = headers.get("x-api-key") or query_params.get("api_key")
    
    # Bypass auth for local development/POC
    # if key != "DEV_POC_TOKEN":
    #     raise HTTPException(status_code=401, detail="Unauthorized. Missing or invalid API key.")
    return key

auth_dep = [Depends(verify_api_key)]

# Mount Routers with Authentication
app.include_router(cameras.router, dependencies=auth_dep)
app.include_router(events.router, dependencies=auth_dep)
app.include_router(vehicles.router, dependencies=auth_dep)
app.include_router(tracking.router, dependencies=auth_dep)
app.include_router(vms.router, dependencies=auth_dep)
app.include_router(alerts.router, dependencies=auth_dep)
app.include_router(analytics.router, dependencies=auth_dep)
app.include_router(video_stream.router, dependencies=auth_dep)
app.include_router(ai_copilot.router, dependencies=auth_dep)
app.include_router(search_upload.router, dependencies=auth_dep)
app.include_router(tactical_ops.router, dependencies=auth_dep)
app.include_router(anomaly_events.router, dependencies=auth_dep)
app.include_router(review.router, dependencies=auth_dep)
app.include_router(ingest.router, dependencies=auth_dep)

# Mount Frontend Static Assets
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

DATA_DIR = POC_DIR / "data"
if DATA_DIR.exists():
    app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.get("/")
def serve_dashboard():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Red EYE Backend API is Running. Frontend not yet initialized."}


@app.get("/health")
def health_check():
    return {
        "status": "HEALTHY",
        "system": "Red EYE Smart City Surveillance Platform",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

