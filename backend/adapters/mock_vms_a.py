"""
Mock VMS Adapter A (Department of Home & Police CSITMS)
Implements standard proprietary SDK/REST adapter interface.
"""

from typing import Dict, List, Any
from .base_adapter import BaseVMSAdapter


class MockVMSAdapterA(BaseVMSAdapter):
    def __init__(self, cluster_id="VMS-CLUSTER-01", name="Gujarat Police CSITMS", endpoint="http://103.250.160.189:8000/vms/police"):
        super().__init__(cluster_id, name, endpoint)

    def get_status(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "name": self.name,
            "adapter": "mock_vms_a",
            "protocol": "Hikvision ISAPI / ONVIF Profile T",
            "health": "ONLINE",
            "uptime_hours": 348.2,
            "active_streams": 18,
            "packet_loss_pct": 0.02
        }

    def list_cameras(self) -> List[Dict[str, Any]]:
        return [
            {"camera_id": "CAM-001", "name": "Ahmedabad Police Junction-01", "resolution": "1920x1080", "status": "ONLINE"},
            {"camera_id": "CAM-002", "name": "Chimanbhai Bridge CSITMS-10", "resolution": "1920x1080", "status": "ONLINE"},
            {"camera_id": "CAM-005", "name": "Visat Teen Rasta CSITMS-31", "resolution": "1920x1080", "status": "ONLINE"}
        ]

    def get_live_stream_uri(self, camera_id: str) -> str:
        cam_map = {
            "CAM-001": "rtsp://103.250.160.189:8554/stream/cam01",
            "CAM-002": "rtsp://103.250.160.189:8554/stream/cam02",
            "CAM-005": "rtsp://103.250.160.189:8554/stream/cam05",
        }
        return cam_map.get(camera_id, f"rtsp://103.250.160.189:8554/stream/cam01")

    def query_recorded_clip(self, camera_id: str, start_time: str, end_time: str) -> str:
        return f"/data/recorded_streams/{camera_id.lower()}.mp4"
