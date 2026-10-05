"""
Mock VMS Adapter B (Smart City ICCC & Transport RTO)
Implements Milestone / Genetec REST & RTSP Federation interface.
"""

from typing import Dict, List, Any
from .base_adapter import BaseVMSAdapter


class MockVMSAdapterB(BaseVMSAdapter):
    def __init__(self, cluster_id="VMS-CLUSTER-02", name="Smart City ICCC VMS", endpoint="http://103.250.160.189:8000/vms/iccc"):
        super().__init__(cluster_id, name, endpoint)

    def get_status(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "name": self.name,
            "adapter": "mock_vms_b",
            "protocol": "Milestone Open Network Bridge / WebRTC",
            "health": "ONLINE",
            "uptime_hours": 712.5,
            "active_streams": 14,
            "packet_loss_pct": 0.01
        }

    def list_cameras(self) -> List[Dict[str, Any]]:
        return [
            {"camera_id": "CAM-004", "name": "ICCC Municipal Zone-04", "resolution": "1920x1080", "status": "ONLINE"},
            {"camera_id": "CAM-006", "name": "Gandhinagar RTO Toll Gantry", "resolution": "1920x1080", "status": "ONLINE"}
        ]

    def get_live_stream_uri(self, camera_id: str) -> str:
        cam_map = {
            "CAM-004": "rtsp://103.250.160.189:8554/stream/cam04",
            "CAM-006": "rtsp://103.250.160.189:8554/stream/cam06",
        }
        return cam_map.get(camera_id, f"rtsp://103.250.160.189:8554/stream/cam04")

    def query_recorded_clip(self, camera_id: str, start_time: str, end_time: str) -> str:
        return f"/data/recorded_streams/{camera_id.lower()}.mp4"
