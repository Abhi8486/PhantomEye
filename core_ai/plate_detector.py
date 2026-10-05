"""
Dedicated License Plate Detector — YOLO-based plate localization with HSV color fallback.
Operates on vehicle crops (full crop, not restricted to lower-55% ROI).
Loaded once as a singleton. Degrades gracefully to HSV-only if the plate model is unavailable.
"""

import os
import cv2
import numpy as np
from typing import Optional, Dict, List, Tuple

# Try to load YOLO — if ultralytics is available (it is, since detector.py uses it)
try:
    from ultralytics import YOLO
    _YOLO_AVAILABLE = True
except ImportError:
    _YOLO_AVAILABLE = False


class PlateDetectionResult:
    """Represents a detected license plate region within a vehicle crop."""
    __slots__ = ("bbox", "confidence", "method", "plate_crop")

    def __init__(self, bbox: Tuple[int, int, int, int], confidence: float,
                 method: str, plate_crop: np.ndarray):
        self.bbox = bbox            # (x1, y1, x2, y2) within the vehicle crop
        self.confidence = confidence
        self.method = method        # "yolo" or "hsv"
        self.plate_crop = plate_crop


class PlateDetector:
    """
    Two-tier license plate detector:
    Tier 1: YOLO-nano plate detection model (if available)
    Tier 2: HSV multi-color masking + contour extraction (fallback)
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, model_path: Optional[str] = None, conf_thresh: float = 0.25):
        if self._initialized:
            return

        self.conf_thresh = conf_thresh
        self.yolo_model = None
        self._yolo_available = False

        # Attempt to load YOLO plate detection model
        if _YOLO_AVAILABLE:
            self._try_load_yolo(model_path)

        if not self._yolo_available:
            print("[PLATE_DETECTOR] YOLO plate model not available. Using HSV-only mode.")
        
        self._initialized = True

    def _try_load_yolo(self, model_path: Optional[str] = None):
        """Attempt to load a YOLO plate detection model from various locations."""
        # Search paths for the plate detection model
        search_paths = []
        if model_path:
            search_paths.append(model_path)

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        search_paths.extend([
            os.path.join(base_dir, "models", "plate_detect.pt"),
            os.path.join(base_dir, "plate_detect.pt"),
            os.path.join(base_dir, "yolov8n_plate.pt"),
            os.path.join(base_dir, "models", "yolov8n_plate.pt"),
        ])

        for path in search_paths:
            if os.path.isfile(path):
                try:
                    print(f"[PLATE_DETECTOR] Loading YOLO plate model from {path}...")
                    self.yolo_model = YOLO(path)
                    self._yolo_available = True
                    print(f"[PLATE_DETECTOR] YOLO plate model loaded successfully!")
                    return
                except Exception as e:
                    print(f"[PLATE_DETECTOR] Failed to load YOLO model from {path}: {e}")

        # Try loading from Ultralytics HUB (keremberke/yolov8n-license-plate-detection)
        try:
            print("[PLATE_DETECTOR] Attempting to load plate model from Ultralytics HUB...")
            self.yolo_model = YOLO("keremberke/yolov8n-license-plate-detection")
            self._yolo_available = True
            print("[PLATE_DETECTOR] HUB plate model loaded successfully!")
        except Exception as e:
            print(f"[PLATE_DETECTOR] HUB model not available: {e}")

    def detect(self, vehicle_crop: np.ndarray) -> Optional[PlateDetectionResult]:
        """
        Detect license plate in a vehicle crop image.

        Args:
            vehicle_crop: BGR image of a detected vehicle (full crop).

        Returns:
            PlateDetectionResult with the plate crop and metadata, or None if no plate found.
        """
        if vehicle_crop is None or vehicle_crop.size == 0:
            return None

        h, w = vehicle_crop.shape[:2]
        if h < 30 or w < 30:
            return None

        # Tier 1: YOLO plate detection (operates on full vehicle crop)
        if self._yolo_available:
            result = self._detect_yolo(vehicle_crop)
            if result is not None:
                return result

        # Tier 2: HSV color masking fallback
        result = self._detect_hsv(vehicle_crop)
        return result

    def _detect_yolo(self, vehicle_crop: np.ndarray) -> Optional[PlateDetectionResult]:
        """YOLO-based plate detection on the full vehicle crop."""
        try:
            h, w = vehicle_crop.shape[:2]
            results = self.yolo_model(
                vehicle_crop,
                imgsz=640,
                conf=self.conf_thresh,
                verbose=False,
                device="cpu"  # CPU-safe for Ryzen 5 5500U
            )[0]

            best_box = None
            best_conf = 0.0

            for box in results.boxes:
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                # Sanity checks
                bw, bh = x2 - x1, y2 - y1
                if bw < 15 or bh < 8:
                    continue
                ar = bw / float(bh) if bh > 0 else 0
                if ar < 0.8 or ar > 8.0:
                    continue

                if conf > best_conf:
                    best_conf = conf
                    best_box = (
                        max(0, x1), max(0, y1),
                        min(w, x2), min(h, y2)
                    )

            if best_box and best_conf >= self.conf_thresh:
                x1, y1, x2, y2 = best_box
                plate_crop = vehicle_crop[y1:y2, x1:x2]
                if plate_crop.size > 0:
                    return PlateDetectionResult(
                        bbox=best_box,
                        confidence=best_conf,
                        method="yolo",
                        plate_crop=plate_crop.copy()
                    )
        except Exception as e:
            print(f"[PLATE_DETECTOR] YOLO detection error: {e}")

        return None

    def _detect_hsv(self, vehicle_crop: np.ndarray) -> Optional[PlateDetectionResult]:
        """
        HSV multi-color masking plate localization (imported from original anpr.py).
        Searches the FULL vehicle crop — not restricted to lower 55%.
        Uses White/Yellow/Green plate color detection + contour extraction.
        """
        try:
            h, w = vehicle_crop.shape[:2]
            hsv = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2HSV)

            # Multi-color plate masks
            # White plates (private vehicles)
            lower_white = np.array([0, 0, 180])
            upper_white = np.array([180, 50, 255])
            mask_white = cv2.inRange(hsv, lower_white, upper_white)

            # Yellow plates (commercial/taxi)
            lower_yellow = np.array([18, 80, 150])
            upper_yellow = np.array([35, 255, 255])
            mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)

            # Green plates (EVs)
            lower_green = np.array([35, 50, 50])
            upper_green = np.array([85, 255, 255])
            mask_green = cv2.inRange(hsv, lower_green, upper_green)

            combined_mask = cv2.bitwise_or(mask_white, mask_yellow)
            combined_mask = cv2.bitwise_or(combined_mask, mask_green)

            # Morphological cleanup
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 3))
            combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)

            # Find plate-like contours
            contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)

            for cnt in contours:
                bx, by, bw, bh = cv2.boundingRect(cnt)
                ar = bw / float(bh) if bh > 0 else 0

                # Plate aspect ratio filter (broadened for EV and multi-line plates)
                if bw >= 20 and bh >= 8 and (1.0 <= ar <= 7.0):
                    # Confidence based on aspect ratio closeness to ideal (3.5:1)
                    ideal_ar = 3.5
                    ar_deviation = abs(ar - ideal_ar) / ideal_ar
                    hsv_confidence = max(0.3, min(0.85, 1.0 - ar_deviation))

                    # Area ratio — plate should be a reasonable fraction of the vehicle
                    area_ratio = (bw * bh) / float(w * h)
                    if area_ratio < 0.005 or area_ratio > 0.4:
                        continue

                    # Pad slightly to capture edge characters
                    pad_x = int(bw * 0.10)
                    pad_y = int(bh * 0.10)
                    x1 = max(0, bx - pad_x)
                    y1 = max(0, by - pad_y)
                    x2 = min(w, bx + bw + pad_x)
                    y2 = min(h, by + bh + pad_y)

                    plate_crop = vehicle_crop[y1:y2, x1:x2]
                    if plate_crop.size > 0:
                        return PlateDetectionResult(
                            bbox=(x1, y1, x2, y2),
                            confidence=hsv_confidence,
                            method="hsv",
                            plate_crop=plate_crop.copy()
                        )

        except Exception as e:
            print(f"[PLATE_DETECTOR] HSV detection error: {e}")

        return None


# Global singleton instance
plate_detector = PlateDetector()
