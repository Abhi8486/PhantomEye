"""
VMS Federation Router (Model 3: VMS Federation & Middleware)
"""

from fastapi import APIRouter, HTTPException
from typing import List
from ..database.schema import get_db_connection
from ..adapters.mock_vms_a import MockVMSAdapterA
from ..adapters.mock_vms_b import MockVMSAdapterB
from ..adapters.rtsp_adapter import RTSPAdapter

router = APIRouter(prefix="/api/vms", tags=["VMS Federation Middleware"])

ADAPTER_REGISTRY = {
    "mock_vms_a": MockVMSAdapterA(),
    "mock_vms_b": MockVMSAdapterB(),
    "rtsp": RTSPAdapter()
}


@router.get("/clusters")
def list_vms_clusters():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM vms_clusters ORDER BY cluster_id ASC;")
    rows = cursor.fetchall()
    conn.close()

    clusters = []
    for r in rows:
        d = dict(r)
        adapter = ADAPTER_REGISTRY.get(d["adapter_type"])
        if adapter:
            d["telemetry"] = adapter.get_status()
        clusters.append(d)

    return {"total": len(clusters), "clusters": clusters}


@router.get("/stream/{camera_id}")
def resolve_camera_stream(camera_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cameras WHERE camera_id = ?;", (camera_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Camera not found in registry")

    adapter_key = row["vms_adapter"] or "rtsp"
    adapter = ADAPTER_REGISTRY.get(adapter_key, ADAPTER_REGISTRY["rtsp"])
    stream_uri = adapter.get_live_stream_uri(camera_id)

    return {
        "camera_id": camera_id,
        "name": row["name"],
        "adapter_type": adapter_key,
        "stream_uri": stream_uri,
        "resolution": row["resolution"],
        "fps": row["fps"],
        "status": row["status"]
    }
