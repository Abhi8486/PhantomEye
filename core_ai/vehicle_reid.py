"""
Lightweight Cross-Camera Vehicle Re-Identification Engine.
Uses multiple signals (plate, appearance, vehicle type, spatiotemporal) for probabilistic matching.

Reuses existing:
  - DeepReIDExtractor (MobileNetV3, 576-d) from reid_extractor.py
  - PersonReIDEngine (HSV histogram, 512-d) from reid_engine.py
  - MultiModalEvidenceFusionEngine (kinematic scoring) from evidence_fusion.py

All matching is probabilistic — never claims "definitely same vehicle".
"""

import time
# pyrefly: ignore [missing-import]
import numpy as np
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from collections import OrderedDict

from core_ai.reid_extractor import DeepReIDExtractor
from core_ai.evidence_fusion import MultiModalEvidenceFusionEngine


@dataclass
class VehicleSignature:
    """A recorded sighting of a vehicle with all available signals."""
    plate_number: Optional[str]     # May be None if OCR failed
    deep_embedding: np.ndarray      # 576-d MobileNetV3 embedding
    vehicle_type: str               # "car", "bus", "truck", "motorcycle", "auto_rickshaw"
    vehicle_color: Optional[str]    # Dominant color string
    camera_id: str
    timestamp: float                # Unix timestamp
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    confidence: float = 0.0         # OCR/detection confidence


@dataclass
class ReIDMatch:
    """A candidate re-identification match."""
    matched_signature: VehicleSignature
    plate_similarity: float         # 0.0 or 1.0 (exact match)
    appearance_similarity: float    # Cosine similarity of deep embeddings
    type_match: float               # 1.0 if same type, 0.0 otherwise
    spatiotemporal_score: float     # Kinematic feasibility
    composite_score: float          # Weighted final score
    confidence_level: str           # HIGH / MODERATE / LOW


# Configuration
MAX_GALLERY_SIZE = 200
GALLERY_MAX_AGE_SEC = 3600  # 1 hour


class VehicleReIDEngine:
    """
    Cross-camera vehicle re-identification using multi-signal fusion.

    Signals (with weights):
      1. Plate match (0.45) — strongest signal, exact string comparison
      2. Visual appearance (0.30) — MobileNetV3 cosine similarity
      3. Vehicle type match (0.15) — categorical comparison
      4. Spatiotemporal feasibility (0.10) — kinematic scoring from evidence_fusion
    """

    def __init__(self):
        self._gallery: OrderedDict[str, VehicleSignature] = OrderedDict()
        self._reid_extractor = DeepReIDExtractor()
        print("[OK] Vehicle Re-ID Engine initialized (MobileNetV3 + Multi-Signal Fusion)")

    def extract_embedding(self, vehicle_crop: np.ndarray) -> np.ndarray:
        """Extract 576-d visual embedding from a vehicle crop."""
        return self._reid_extractor.extract_embedding(vehicle_crop)

    def register(self, plate: Optional[str], embedding: np.ndarray,
                 vehicle_type: str, vehicle_color: Optional[str],
                 camera_id: str, timestamp: float,
                 latitude: Optional[float] = None, longitude: Optional[float] = None,
                 confidence: float = 0.0):
        """
        Register a confirmed vehicle sighting in the gallery.

        Args:
            plate: Confirmed plate number (or None if OCR failed).
            embedding: 576-d visual embedding.
            vehicle_type: Vehicle class string.
            vehicle_color: Dominant color.
            camera_id: Camera where sighted.
            timestamp: Unix timestamp of sighting.
            latitude, longitude: Camera coordinates (if available).
            confidence: Detection confidence.
        """
        sig = VehicleSignature(
            plate_number=plate,
            deep_embedding=embedding,
            vehicle_type=vehicle_type.lower() if vehicle_type else "unknown",
            vehicle_color=vehicle_color,
            camera_id=camera_id,
            timestamp=timestamp,
            latitude=latitude,
            longitude=longitude,
            confidence=confidence,
        )

        # Key by plate if available, otherwise by timestamp hash
        key = plate if plate else f"unk_{camera_id}_{int(timestamp*1000)}"
        self._gallery[key] = sig

        # Enforce gallery size limit (LRU eviction)
        while len(self._gallery) > MAX_GALLERY_SIZE:
            self._gallery.popitem(last=False)

    def query(self, plate: Optional[str], embedding: np.ndarray,
              vehicle_type: str, vehicle_color: Optional[str],
              camera_id: str, timestamp: float,
              latitude: Optional[float] = None, longitude: Optional[float] = None,
              top_k: int = 5) -> List[ReIDMatch]:
        """
        Find candidate re-ID matches in the gallery.

        Returns top-k matches sorted by composite score, excluding same-camera
        sightings within a short time window (to avoid self-matching).
        """
        if not self._gallery:
            return []

        matches = []
        vehicle_type_lower = vehicle_type.lower() if vehicle_type else "unknown"

        for key, sig in self._gallery.items():
            # Skip self-matching (same camera within 30 seconds)
            if sig.camera_id == camera_id and abs(sig.timestamp - timestamp) < 30.0:
                continue

            # 1. Plate similarity (exact match or nothing)
            plate_sim = 0.0
            if plate and sig.plate_number and plate == sig.plate_number:
                plate_sim = 1.0
            elif plate and sig.plate_number:
                # Partial match — count common characters
                common = sum(1 for a, b in zip(plate, sig.plate_number) if a == b)
                max_len = max(len(plate), len(sig.plate_number))
                if max_len > 0:
                    ratio = common / max_len
                    plate_sim = ratio if ratio >= 0.7 else 0.0  # Only count if >70% match

            # 2. Appearance similarity (cosine)
            appearance_sim = 0.0
            if embedding is not None and sig.deep_embedding is not None:
                n1 = np.linalg.norm(embedding)
                n2 = np.linalg.norm(sig.deep_embedding)
                if n1 > 1e-6 and n2 > 1e-6:
                    dot = float(np.dot(embedding, sig.deep_embedding) / (n1 * n2))
                    appearance_sim = max(0.0, min(1.0, (dot + 1.0) / 2.0))

            # 3. Type match
            type_match = 1.0 if vehicle_type_lower == sig.vehicle_type else 0.0

            # 4. Spatiotemporal feasibility
            spatio_score = 0.5  # Default if no coordinates
            if (latitude is not None and longitude is not None and
                    sig.latitude is not None and sig.longitude is not None):
                try:
                    from datetime import datetime
                    origin_time = datetime.fromtimestamp(sig.timestamp)
                    dest_time = datetime.fromtimestamp(timestamp)
                    score, _, _ = MultiModalEvidenceFusionEngine.calculate_spatio_temporal_score(
                        sig.latitude, sig.longitude, origin_time,
                        latitude, longitude, dest_time,
                    )
                    spatio_score = score
                except Exception:
                    spatio_score = 0.5

            # Weighted composite score
            composite = (
                0.45 * plate_sim +
                0.30 * appearance_sim +
                0.15 * type_match +
                0.10 * spatio_score
            )

            # Determine confidence level
            if composite >= 0.85:
                conf_level = "HIGH"
            elif composite >= 0.65:
                conf_level = "MODERATE"
            else:
                conf_level = "LOW"

            # Only include if there's some evidence
            if composite >= 0.30:
                matches.append(ReIDMatch(
                    matched_signature=sig,
                    plate_similarity=round(plate_sim, 3),
                    appearance_similarity=round(appearance_sim, 3),
                    type_match=type_match,
                    spatiotemporal_score=round(spatio_score, 3),
                    composite_score=round(composite, 3),
                    confidence_level=conf_level,
                ))

        # Sort by composite score, descending
        matches.sort(key=lambda m: m.composite_score, reverse=True)
        return matches[:top_k]

    def cleanup_old(self, max_age_seconds: float = GALLERY_MAX_AGE_SEC):
        """Remove gallery entries older than max_age_seconds."""
        now = time.time()
        expired_keys = [
            k for k, sig in self._gallery.items()
            if now - sig.timestamp > max_age_seconds
        ]
        for k in expired_keys:
            del self._gallery[k]

    @property
    def gallery_size(self) -> int:
        return len(self._gallery)


# Global singleton
vehicle_reid = VehicleReIDEngine()
