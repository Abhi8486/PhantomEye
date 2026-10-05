"""
Alerts & Real-time WebSocket Router (Model 2 & Layer 3: Watchlist Alerts & Threat Momentum)
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from typing import List, Optional
import json
import asyncio
from datetime import datetime
from ..database.schema import get_db_connection

router = APIRouter(prefix="/api/alerts", tags=["Watchlist Alerts & WebSocket"])


class AlertConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._loop = None

    async def connect(self, websocket: WebSocket):
        try:
            self._loop = asyncio.get_running_loop()
        except Exception:
            pass
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

    def broadcast_sync(self, message: dict):
        """
        Thread-safe synchronous broadcast callable from worker threads, AI pipelines, or background tasks.
        """
        if not self.active_connections:
            return
        try:
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self.broadcast(message), self._loop)
            else:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
                    else:
                        loop.run_until_complete(self.broadcast(message))
                except Exception:
                    pass
        except Exception:
            pass


alert_manager = AlertConnectionManager()


@router.get("")
def list_alerts(
    alert_level: Optional[str] = None,
    is_acknowledged: Optional[int] = None,
    limit: int = 50
):
    conn = get_db_connection()
    cursor = conn.cursor()

    sql = """
    SELECT a.*, c.name as camera_name, c.city, c.department, c.latitude, c.longitude
    FROM alerts a
    JOIN cameras c ON a.camera_id = c.camera_id
    WHERE 1=1
    """
    params = []

    if alert_level:
        sql += " AND a.alert_level = ?"
        params.append(alert_level.upper())
    if is_acknowledged is not None:
        sql += " AND a.is_acknowledged = ?"
        params.append(is_acknowledged)

    sql += " ORDER BY a.timestamp DESC LIMIT ?"
    params.append(limit)

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["metadata"] = json.loads(d["metadata_json"]) if d.get("metadata_json") else {}
        result.append(d)

    return {"total": len(result), "alerts": result}


@router.post("/{alert_id}/ack")
async def acknowledge_alert(alert_id: str, operator_name: str = "Command Officer"):
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().isoformat()
    cursor.execute("""
    UPDATE alerts
    SET is_acknowledged = 1, acknowledged_by = ?, acknowledged_at = ?
    WHERE alert_id = ?;
    """, (operator_name, now_str, alert_id))
    conn.commit()
    conn.close()

    # Broadcast update via WebSocket
    await alert_manager.broadcast({
        "type": "ALERT_ACKNOWLEDGED",
        "alert_id": alert_id,
        "operator": operator_name,
        "timestamp": now_str
    })

    return {"status": "SUCCESS", "alert_id": alert_id, "acknowledged_by": operator_name}


@router.websocket("/ws")
async def websocket_alerts_endpoint(websocket: WebSocket):
    await alert_manager.connect(websocket)
    try:
        # Send initial connection acknowledgment
        await websocket.send_json({
            "type": "CONNECTION_ESTABLISHED",
            "message": "Connected to PhantomEye Real-Time Tactical Alert Stream",
            "timestamp": datetime.now().isoformat()
        })
        while True:
            # Keep alive and receive client messages (heartbeat/ack)
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "PING":
                    await websocket.send_json({"type": "PONG", "timestamp": datetime.now().isoformat()})
            except Exception:
                pass
    except WebSocketDisconnect:
        alert_manager.disconnect(websocket)
