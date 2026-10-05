"""
Abstract Base VMS Adapter Contract (Model 3 Middleware Federation)
Allows the central system to ingest metadata and control streams
from heterogeneous departmental VMSs (Hikvision, Milestone, Genetec, Dahua, RTSP).
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any


class BaseVMSAdapter(ABC):
    def __init__(self, cluster_id: str, name: str, endpoint_url: str):
        self.cluster_id = cluster_id
        self.name = name
        self.endpoint_url = endpoint_url

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Returns health, connectivity, and telemetry of the VMS cluster."""
        pass

    @abstractmethod
    def list_cameras(self) -> List[Dict[str, Any]]:
        """Discovers and returns all camera nodes managed by this VMS."""
        pass

    @abstractmethod
    def get_live_stream_uri(self, camera_id: str) -> str:
        """Returns the normalized RTSP / HLS / WebRTC streaming URI."""
        pass

    @abstractmethod
    def query_recorded_clip(self, camera_id: str, start_time: str, end_time: str) -> str:
        """Requests playback clip from local departmental storage."""
        pass
