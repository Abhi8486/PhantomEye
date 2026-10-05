import urllib.request
import json
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from ..database.schema import get_db_connection

router = APIRouter(prefix="/api/ingest", tags=["Ingest"])

@router.get("")
def get_ingest_cameras():
    """
    Returns the list of cameras and their per-camera properties by proxying from the master source.
    Falls back to local DB if remote is unavailable.
    """
    try:
        url = "https://cctv.corp8.cloud/cameras.json"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
            'Accept': 'application/json'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            raw_data = json.loads(response.read().decode('utf-8'))
            normalized_data = []
            for item in raw_data:
                raw_id = item.get("id", "")
                if raw_id.startswith("cam"):
                    num = raw_id.replace("cam", "")
                    cam_id = f"CAM-{num.zfill(3)}"
                else:
                    cam_id = raw_id
                normalized_data.append({
                    "camera_id": cam_id,
                    "name": item.get("name", "")
                })
            return JSONResponse(content=normalized_data)
    except Exception as e:
        print(f"[Ingest API] Remote fetch failed ({e}), falling back to local DB")
        try:
            conn = get_db_connection()
            rows = conn.execute("SELECT * FROM cameras ORDER BY camera_id ASC").fetchall()
            conn.close()
            cameras = [dict(row) for row in rows]
            return JSONResponse(content=cameras)
        except Exception as db_e:
            return JSONResponse(status_code=500, content={"error": str(db_e)})
