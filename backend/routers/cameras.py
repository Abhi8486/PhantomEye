"""
Camera Registry Router (Model 1: Central CCTV Registry & GIS Mapping)
Provides clean operational status:
- ACTIVE (Camera working & operational)
- DEACTIVE (Camera link disconnected / blocked view / offline)
"""

import json
import time
import csv
import io
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from ..database.schema import get_db_connection
from core_ai.indexer import _OFFLINE_RTSP_CAMS, _CACHE_LOCK

router = APIRouter(prefix="/api/cameras", tags=["Central CCTV Registry"])


@router.get("")
def list_cameras(
    department: Optional[str] = None,
    city: Optional[str] = None,
    status: Optional[str] = None
):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM cameras WHERE 1=1"
    params = []

    if department:
        query += " AND department = ?"
        params.append(department)
    if city:
        query += " AND city = ?"
        params.append(city)

    query += " ORDER BY camera_id ASC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d["tags"]) if d.get("tags") else []
        
        # Clean binary status: ACTIVE vs DEACTIVE
        is_active = (d.get("status") == "ACTIVE")
        d["operational_status"] = "ACTIVE" if is_active else "DEACTIVE"
        d["status_label"] = "ACTIVE" if is_active else "DEACTIVE"
        d["color_code"] = "#00e676" if is_active else "#ff1744"

        if status and d["operational_status"] != status:
            continue

        result.append(d)

    return {"total": len(result), "cameras": result}


@router.get("/departments")
def get_department_counts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT department, COUNT(*) as camera_count,
               SUM(CASE WHEN status='ACTIVE' THEN 1 ELSE 0 END) as active_count
        FROM cameras
        GROUP BY department
        ORDER BY camera_count DESC;
    """)
    rows = cursor.fetchall()
    conn.close()
    return {"departments": [dict(r) for r in rows]}

@router.get("/realtime_status")
def get_realtime_status():
    """Returns a list of cameras currently known to be offline by the AI backend."""
    now = time.time()
    offline_cams = []
    
    with _CACHE_LOCK:
        for cid, ts in _OFFLINE_RTSP_CAMS.items():
            # The backend caches offline state for 60 seconds
            if (now - ts) < 60.0:
                offline_cams.append(cid)
                
    return {"offline_cameras": offline_cams}

class CameraLocationUpdate(BaseModel):
    latitude: float
    longitude: float

@router.put("/{camera_id}/location")
def update_camera_location(camera_id: str, data: CameraLocationUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE cameras SET latitude = ?, longitude = ? WHERE camera_id = ?",
        (data.latitude, data.longitude, camera_id)
    )
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    
    if rows_affected == 0:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    return {"success": True, "message": "Location updated successfully"}

@router.post("/upload_csv")
async def upload_cameras_csv(file: UploadFile = File(...)):
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    
    content = await file.read()
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Invalid file encoding. Please upload a UTF-8 CSV.")
        
    reader = csv.DictReader(io.StringIO(decoded))
    
    required_cols = {"camera_id", "name", "latitude", "longitude"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        raise HTTPException(status_code=400, detail=f"CSV must contain at least the following columns: {', '.join(required_cols)}")
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    success_count = 0
    for row in reader:
        try:
            lat = float(row["latitude"])
            lng = float(row["longitude"])
            cam_id = row["camera_id"].strip()
            name = row["name"].strip()
            department = row.get("department", "Unknown").strip()
            vms_vendor = row.get("vms_vendor", "Generic").strip()
            city = row.get("city", "Unknown").strip()
            status = row.get("status", "ACTIVE").strip()
            stream_url = row.get("stream_url", "").strip()
            
            cursor.execute("""
                INSERT INTO cameras (
                    camera_id, name, department, vms_vendor, city, latitude, longitude, status, stream_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(camera_id) DO UPDATE SET
                    name = excluded.name,
                    department = excluded.department,
                    vms_vendor = excluded.vms_vendor,
                    city = excluded.city,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    status = excluded.status,
                    stream_url = excluded.stream_url
            """, (cam_id, name, department, vms_vendor, city, lat, lng, status, stream_url))
            success_count += 1
        except Exception as e:
            print(f"Error processing row {row}: {e}")
            
    conn.commit()
    conn.close()
    
    return {"success": True, "message": f"Successfully processed {success_count} cameras"}
