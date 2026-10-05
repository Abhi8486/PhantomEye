"""
PhantomEye Database Schema & Data Access Layer
Stores Central CCTV Registry (50 cameras across 26 departments),
AI Events, ANPR Detections, Watchlist Alerts, and VMS Configurations.
"""

import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "phantomeye.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Central CCTV Registry (Model 1 Base)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cameras (
        camera_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        department TEXT NOT NULL,
        vms_vendor TEXT NOT NULL,
        location_name TEXT NOT NULL,
        city TEXT NOT NULL,
        district TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        heading_angle REAL DEFAULT 0.0,
        fov_angle REAL DEFAULT 70.0,
        coverage_radius REAL DEFAULT 80.0,
        resolution TEXT DEFAULT '1920x1080',
        fps INTEGER DEFAULT 25,
        stream_url TEXT NOT NULL,
        vms_adapter TEXT DEFAULT 'rtsp',
        status TEXT DEFAULT 'ACTIVE',
        last_heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tags TEXT DEFAULT '[]',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. AI Video Events (Model 2 Metadata Analytics)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        camera_id TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        event_type TEXT NOT NULL,
        track_id TEXT,
        object_class TEXT NOT NULL,
        confidence REAL NOT NULL,
        bbox_json TEXT,
        attributes_json TEXT,
        snapshot_path TEXT,
        FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
    );
    """)

    # 3. Vehicle & ANPR Records (Model 2 ANPR + VAHAN)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vehicle_anpr (
        anpr_id TEXT PRIMARY KEY,
        camera_id TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        plate_number TEXT NOT NULL,
        confidence REAL NOT NULL,
        vehicle_type TEXT DEFAULT 'Car',
        vehicle_color TEXT DEFAULT 'White',
        direction TEXT DEFAULT 'Inbound',
        speed_kmh REAL DEFAULT 45.0,
        vahan_owner TEXT,
        vahan_model TEXT,
        vahan_status TEXT DEFAULT 'NOMINAL',
        is_flagged INTEGER DEFAULT 0,
        fir_reference TEXT,
        bbox_json TEXT,
        snapshot_path TEXT,
        FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
    );
    """)

    # 4. Watchlist Alerts & Threat Momentum (TMS)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        alert_id TEXT PRIMARY KEY,
        camera_id TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        alert_level TEXT NOT NULL, -- INFO, WARNING, CRITICAL
        alert_type TEXT NOT NULL,  -- WEAPON, WANTED_VEHICLE, STOLEN_VEHICLE, SUSPECT_FACE
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        target_identifier TEXT,
        tms_score REAL DEFAULT 10.0,
        is_acknowledged INTEGER DEFAULT 0,
        acknowledged_by TEXT,
        acknowledged_at TIMESTAMP,
        metadata_json TEXT,
        FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
    );
    """)

    # 5. VMS Federation Adapters (Model 3 Middleware)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vms_clusters (
        cluster_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        department TEXT NOT NULL,
        adapter_type TEXT NOT NULL, -- mock_vms_a, mock_vms_b, milestone, hikvision
        endpoint_url TEXT NOT NULL,
        camera_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'ONLINE',
        last_sync TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 6. Granular Per-Frame Plate Reads (ANPR v2 — raw OCR history)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS plate_reads (
        read_id TEXT PRIMARY KEY,
        vehicle_track_id INTEGER,
        camera_id TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        plate_text TEXT NOT NULL,
        ocr_confidence REAL,
        plate_detection_confidence REAL,
        quality_score REAL,
        format_validation TEXT,
        detection_method TEXT,
        image_path TEXT,
        FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
    );
    """)

    # 7. Vehicle Movement Events
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS vehicle_events (
        event_id TEXT PRIMARY KEY,
        camera_id TEXT NOT NULL,
        vehicle_track_id INTEGER,
        plate_number TEXT,
        event_type TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        direction TEXT,
        estimated_speed_kmh REAL,
        dwell_seconds REAL,
        lane TEXT,
        metadata_json TEXT,
        FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
    );
    """)

    # 8. Manual Review Queue for Low-Confidence ANPR Detections
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS review_queue (
        review_id TEXT PRIMARY KEY,
        anpr_id TEXT,
        camera_id TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        original_plate_text TEXT NOT NULL,
        ocr_confidence REAL,
        quality_score REAL,
        image_path TEXT,
        review_status TEXT DEFAULT 'PENDING',
        corrected_plate_text TEXT,
        reviewed_by TEXT,
        reviewed_at TIMESTAMP,
        notes TEXT,
        FOREIGN KEY (camera_id) REFERENCES cameras(camera_id)
    );
    """)

    # Safe ALTER TABLE: Add new columns to vehicle_anpr (non-breaking migration)
    new_anpr_columns = [
        ("plate_detection_confidence", "REAL"),
        ("quality_score", "REAL"),
        ("format_validation", "TEXT"),
        ("detection_method", "TEXT"),
        ("multi_frame_agreement", "REAL"),
        ("review_status", "TEXT DEFAULT 'AUTO_CONFIRMED'"),
    ]
    for col_name, col_type in new_anpr_columns:
        try:
            cursor.execute(f"ALTER TABLE vehicle_anpr ADD COLUMN {col_name} {col_type};")
        except Exception:
            pass  # Column already exists

    # Create Indexes for lightning-fast sub-5ms queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_cam ON events(camera_id, timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anpr_plate ON vehicle_anpr(plate_number);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anpr_time ON vehicle_anpr(timestamp DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(timestamp DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cameras_dept ON cameras(department);")
    # New indexes for v2 tables
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_plate_reads_cam ON plate_reads(camera_id, timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_plate_reads_text ON plate_reads(plate_text);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_vehicle_events_cam ON vehicle_events(camera_id, timestamp);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_status ON review_queue(review_status);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_anpr_review ON vehicle_anpr(review_status);")

    conn.commit()
    conn.close()
    print(f"[OK] Database schema initialized at {DB_PATH} (v2 — with plate_reads, vehicle_events, review_queue)")


if __name__ == "__main__":
    init_db()
