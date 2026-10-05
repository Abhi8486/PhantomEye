"""
Events Router (Model 2: Metadata Analytics & Ingestion)
"""

from fastapi import APIRouter, Query
from typing import Optional
import json
from ..database.schema import get_db_connection

router = APIRouter(prefix="/api/events", tags=["Metadata Events"])


@router.get("")
def list_events(
    camera_id: Optional[str] = None,
    object_class: Optional[str] = None,
    limit: int = Query(50, le=200)
):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM events WHERE 1=1"
    params = []

    if camera_id:
        query += " AND camera_id = ?"
        params.append(camera_id)
    if object_class:
        query += " AND object_class = ?"
        params.append(object_class)

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["bbox"] = json.loads(d["bbox_json"]) if d.get("bbox_json") else []
        d["attributes"] = json.loads(d["attributes_json"]) if d.get("attributes_json") else {}
        result.append(d)

    return {"total": len(result), "events": result}
