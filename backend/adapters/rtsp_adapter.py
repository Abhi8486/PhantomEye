"""
Standard RTSP / ONVIF Edge Adapter
Direct low-latency streaming adapter for edge nodes and local DVRs.
"""

from typing import Dict, List, Any
from .base_adapter import BaseVMSAdapter


class RTSPAdapter(BaseVMSAdapter):
    def __init__(self, cluster_id="RTSP-EDGE-01", name="Direct RTSP Edge Gateway", endpoint="rtsp://103.250.160.189:8554"):
        super().__init__(cluster_id, name, endpoint)

    def get_status(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "name": self.name,
            "adapter": "rtsp",
            "protocol": "RTSP / RTP / H.264",
            "health": "ONLINE",
            "uptime_hours": 1204.0,
            "active_streams": 30,
            "packet_loss_pct": 0.00
        }

    def list_cameras(self) -> List[Dict[str, Any]]:
        return [{"camera_id": f"CAM-{i:03d}", "status": "ONLINE"} for i in range(1, 31)]

    def get_live_stream_uri(self, camera_id: str) -> str:
        idx = int(camera_id.replace("CAM-", "")) if "CAM-" in camera_id else 1
        return f"rtsp://103.250.160.189:8554/stream/cam{idx:02d}"

    def query_recorded_clip(self, camera_id: str, start_time: str, end_time: str) -> str:
        return f"/data/recorded_streams/{camera_id.lower()}.mp4"
