"""
High-Speed Automatic Number Plate Recognition (ANPR) & VAHAN Cross-Reference
Extracts Indian vehicle registration numbers and queries VAHAN records.

Pipeline (v2):
  Vehicle Crop → Plate Detector (YOLO/HSV) → Perspective Correction →
  Quality Scoring → Quality Gate → Enhancement → EasyOCR → Format Validation →
  VAHAN Enrichment → Result with separated confidence fields

Original single-frame pipeline preserved; multi-frame fusion handled externally
by ocr_fusion.py (called from video_stream.py worker).
"""

import os
import time
import re
import cv2
import torch
import easyocr

from core_ai.plate_detector import plate_detector
from core_ai.plate_preprocessor import (
    correct_perspective, enhance_plate, score_quality,
    QUALITY_GATE_THRESHOLD
)
from core_ai.plate_validator import validate_plate
import numpy as np

# Set to True to save vehicle and plate crops to data/best-frames/ and data/plate_crops/
SAVE_DEBUG_FRAMES = False

def calculate_vehicle_quality(vehicle_crop, bbox, frame_shape, det_confidence):
    """
    Evaluates the quality of a vehicle crop for ANPR suitability.
    Returns a normalized score [0.0, 1.0].
    """
    if vehicle_crop is None or vehicle_crop.size == 0:
        return 0.0
    
    vh, vw = vehicle_crop.shape[:2]
    fh, fw = frame_shape[:2]
    
    # 1. Size Score (0-1) - normalize against a reasonable max size (e.g., 40% of frame)
    target_area = (fw * 0.4) * (fh * 0.4)
    area = vw * vh
    size_score = min(1.0, area / max(1.0, target_area))
    
    # 2. Sharpness Score (0-1)
    gray = cv2.cvtColor(vehicle_crop, cv2.COLOR_BGR2GRAY)
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    sharpness_score = min(1.0, variance / 1000.0) 
    
    # 3. Brightness Score (0-1)
    mean_val = np.mean(gray)
    if mean_val < 40:
        brightness_score = mean_val / 40.0
    elif mean_val > 240:
        brightness_score = (255.0 - mean_val) / 15.0
    else:
        brightness_score = 1.0 - 0.2 * (abs(mean_val - 128) / 128.0)
        
    # 4. Visibility/Boundary Score (0-1)
    x1, y1, x2, y2 = bbox
    visibility_score = 1.0
    if x1 <= 5 or y1 <= 5 or x2 >= fw - 5 or y2 >= fh - 5:
        visibility_score = 0.6
        
    # 5. Combine metrics
    final_score = (
        0.35 * sharpness_score +
        0.25 * size_score +
        0.15 * brightness_score +
        0.15 * visibility_score +
        0.10 * det_confidence
    )
    
    return min(1.0, max(0.0, final_score))



VAHAN_DATABASE = {
    "GJ01AB1234": {
        "owner": "Ramesh Patel",
        "make_model": "Toyota Fortuner (7-Seater)",
        "color": "White",
        "rto": "Ahmedabad West RTO (GJ-01)",
        "status": "🚨 WANTED IN eGujCop",
        "is_flagged": True,
        "fir_ref": "FIR #402/2026 (Crime Branch Gandhinagar)"
    },
    "GJ27AX9999": {
        "owner": "Vikram Thakor",
        "make_model": "Mahindra Scorpio-N",
        "color": "Black",
        "rto": "Ahmedabad East (GJ-27)",
        "status": "🚨 WANTED IN eGujCop",
        "is_flagged": True,
        "fir_ref": "FIR #189/2026 (Vehicle Theft Gang)"
    },
    "GJ18ZZ7777": {
        "owner": "Devang Shah",
        "make_model": "Hyundai Creta",
        "color": "White",
        "rto": "Gandhinagar (GJ-18)",
        "status": "🚨 STOLEN VEHICLE ALERT",
        "is_flagged": True,
        "fir_ref": "FIR #108/2026 (Stolen Vehicle Registry)"
    },
    "GJ05CD5678": {
        "owner": "Salim Khan",
        "make_model": "Bajaj Compact RE (Auto)",
        "color": "Yellow/Green",
        "rto": "Surat RTO (GJ-05)",
        "status": "PUC EXPIRED",
        "is_flagged": False,
        "fir_ref": None
    },
    "GJ06EF4321": {
        "owner": "Anjali Sharma",
        "make_model": "Maruti Suzuki Swift",
        "color": "Silver",
        "rto": "Vadodara RTO (GJ-06)",
        "status": "NOMINAL",
        "is_flagged": False,
        "fir_ref": None
    },
    "GJ27E5539": {
        "owner": "Ramdhani Travels (Gujarat)",
        "make_model": "Ashok Leyland Falcon Deluxe AC Sleeper Bus",
        "color": "White / Blue Commercial",
        "rto": "Gandhinagar RTO (GJ-27)",
        "status": "VALID COMMERCIAL PERMIT",
        "is_flagged": False,
        "fir_ref": None
    },
    "GJ01KZ9901": {
        "owner": "Gujarat Logistics Freight Corp",
        "make_model": "Tata Prima 4028.S Container Truck",
        "color": "Blue / Orange",
        "rto": "Ahmedabad RTO (GJ-01)",
        "status": "ACTIVE TOLL FASTAG PERMIT",
        "is_flagged": False,
        "fir_ref": None
    },
    "GJ01AW6670": {
        "owner": "Rameshchandra Patel",
        "make_model": "Bajaj Compact 4S CNG Auto-Rickshaw",
        "color": "Yellow / Green",
        "rto": "Ahmedabad RTO (GJ-01)",
        "status": "VALID PERMIT",
        "is_flagged": False,
        "fir_ref": None
    }
}


class ANPREngine:
    def __init__(self, use_gpu=True):
        self.device = torch.cuda.is_available() and use_gpu
        print(f"[*] Loading ANPR OCR Engine on GPU={self.device}...")
        self.reader = easyocr.Reader(['en'], gpu=self.device, verbose=False)
        print("[OK] ANPR OCR Engine Ready!")
        self.vehicle_buffers = {}

    def process_vehicle_frame(self, vehicle_key, vehicle_type, vehicle_crop, frame_number, bbox, frame_shape, det_confidence):
        """
        Evaluate and store the best frame for a specific vehicle.
        """
        if vehicle_key not in self.vehicle_buffers:
            self.vehicle_buffers[vehicle_key] = {
                "vehicle_type": vehicle_type,
                "best_frame": None,
                "best_score": 0.0,
                "best_frame_number": None,
                "last_seen_frame": frame_number,
                "total_frames_seen": 0
            }
            # print(f"[ANPR] New vehicle: {vehicle_key}")
            
        vehicle = self.vehicle_buffers[vehicle_key]
        vehicle["last_seen_frame"] = frame_number
        vehicle["total_frames_seen"] += 1
        
        # Calculate true quality using actual frame bounds and box
        if vehicle_crop is not None and vehicle_crop.size > 0:
            q_score = calculate_vehicle_quality(vehicle_crop, bbox, frame_shape, det_confidence)
            
            if q_score > vehicle["best_score"]:
                vehicle["best_score"] = q_score
                vehicle["best_frame"] = vehicle_crop.copy()
                vehicle["best_frame_number"] = frame_number
                # print(f"[ANPR] Updated best frame: {vehicle_key} | score={q_score:.2f} | frame={frame_number}")

    def get_best_frame(self, vehicle_key):
        """Returns the best frame so far without finalizing the buffer."""
        if vehicle_key not in self.vehicle_buffers:
            return None, 0
        vehicle = self.vehicle_buffers[vehicle_key]
        return vehicle["best_frame"], vehicle["total_frames_seen"]

    def finalize_vehicle(self, vehicle_key):
        """
        Extract the final best frame, save to disk, and remove buffer.
        Also automatically detects plates, extracts crops, and logs results.
        """
        if vehicle_key not in self.vehicle_buffers:
            return None
            
        vehicle = self.vehicle_buffers[vehicle_key]
        best_frame = vehicle["best_frame"]
        
        if best_frame is not None:
            frame_num = vehicle["best_frame_number"]
            # print(f"[ANPR] Vehicle finalized: {vehicle_key} | best_frame={frame_num} | score={vehicle['best_score']:.2f}")
            
        # Clean up
        del self.vehicle_buffers[vehicle_key]
        return best_frame

    def read_plate(self, vehicle_crop, allow_gemini_fallback: bool = True):
        """
        Single-frame plate reading pipeline (v2).

        New pipeline:
          1. Plate detection (YOLO or HSV fallback) on FULL vehicle crop
          2. Perspective correction on detected plate region
          3. Quality scoring (gate: skip OCR if quality < threshold)
          4. Image enhancement (CLAHE + sharpening)
          5. EasyOCR with allowlist
          6. Format validation via plate_validator
          7. VAHAN enrichment
          8. Returns result with separated confidence fields

        Returns dict with:
          - plate: str
          - ocr_confidence: float (from EasyOCR)
          - plate_detection_confidence: float (from plate detector)
          - quality_score: float (from quality scorer)
          - format_validation: str ("PASS"/"PARTIAL"/"FAIL")
          - detection_method: str ("yolo+easyocr"/"hsv+easyocr"/"gemini")
          - vahan: dict
          - confidence: float (backward-compatible, same as ocr_confidence)
        Or None if no plate detected.
        """
        if vehicle_crop is None or vehicle_crop.size == 0:
            return None
        vh, vw = vehicle_crop.shape[:2]
        if vh < 25 or vw < 25:
            return None

        # --- Stage 1: Plate Detection (full vehicle crop, not lower 55%) ---
        plate_result = plate_detector.detect(vehicle_crop)
        det_method = "unknown"
        plate_det_confidence = 0.0

        if plate_result is not None:
            plate_crop = plate_result.plate_crop
            plate_det_confidence = plate_result.confidence
            det_method = plate_result.method
        else:
            # No plate detected by either tier — use full vehicle lower region as last resort
            scan_area = vehicle_crop[int(vh * 0.45):, :] if vh > 50 else vehicle_crop
            plate_crop = scan_area
            det_method = "roi_fallback"
            plate_det_confidence = 0.2

        # --- User Request: Save Best Frames and Plate Crops for Inspection ---
        if SAVE_DEBUG_FRAMES:
            try:
                now_ts = int(time.time() * 1000)
                os.makedirs("data/best-frames", exist_ok=True)
                os.makedirs("data/plate_crops", exist_ok=True)
                if vehicle_crop is not None and vehicle_crop.size > 0:
                    cv2.imwrite(f"data/best-frames/best_frame_{now_ts}.jpg", vehicle_crop)
                if plate_crop is not None and plate_crop.size > 0:
                    cv2.imwrite(f"data/plate_crops/plate_crop_{now_ts}.jpg", plate_crop)
            except Exception:
                pass

        # --- Stage 2: Perspective Correction ---
        if det_method != "roi_fallback":
            corrected_crop, was_corrected = correct_perspective(plate_crop)
        else:
            corrected_crop = plate_crop
            was_corrected = False

        # --- Stage 3: Quality Scoring ---
        quality = score_quality(corrected_crop, detection_confidence=plate_det_confidence)

        # Quality Gate: skip OCR if quality is too low (wait for a better frame)
        # Bypassed if Gemini is allowed, since Gemini can read very blurry plates
        if quality.overall < QUALITY_GATE_THRESHOLD and not allow_gemini_fallback:
            return None

        # --- Stage 4: Image Enhancement ---
        enhanced, raw_upscaled = enhance_plate(corrected_crop)

        # --- Stage 5: EasyOCR ---
        results_enhanced = self.reader.readtext(enhanced, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        results_raw = self.reader.readtext(corrected_crop, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        
        # Combine results to give OCR Fusion maximum options
        results = results_enhanced + results_raw

        # --- Stage 6: Extract best candidate ---
        # Try single-line candidates first
        for bbox, text, conf in results:
            clean = re.sub(r'[^A-Za-z0-9]', '', text).upper()
            if len(clean) >= 8 and conf >= 0.5:
                validation = validate_plate(clean)
                if validation.is_valid:
                    return self._build_anpr_record_v2(
                        clean, conf, plate_det_confidence,
                        quality.overall, validation, det_method + "+easyocr"
                    )

        # Try multi-line combination (e.g., Line 1: GJ27, Line 2: E5539)
        if len(results) >= 2:
            sorted_lines = sorted(results, key=lambda x: min([pt[1] for pt in x[0]]))
            combined_str = "".join([re.sub(r'[^A-Za-z0-9]', '', line[1]).upper() for line in sorted_lines])
            
            # Avoid divide by zero
            if len(sorted_lines) > 0:
                avg_conf = sum([line[2] for line in sorted_lines]) / len(sorted_lines)

                if avg_conf >= 0.4 and len(combined_str) >= 8:
                    validation = validate_plate(combined_str)
                    if validation.is_valid:
                        return self._build_anpr_record_v2(
                            combined_str, avg_conf, plate_det_confidence,
                            quality.overall, validation, det_method + "+easyocr_multi"
                        )

        # Return raw OCR result even if format validation fails, but with lower confidence
        # This lets multi-frame fusion and error correction have a chance to fix it
        best_candidate = None
        best_conf = 0.0
        for bbox, text, conf in results:
            clean = re.sub(r'[^A-Za-z0-9]', '', text).upper()
            # A valid Indian plate MUST contain at least one digit and one letter
            has_digit = any(c.isdigit() for c in clean)
            has_alpha = any(c.isalpha() for c in clean)
            if len(clean) >= 6 and conf > best_conf and has_digit and has_alpha:
                best_candidate = clean
                best_conf = conf

        if best_candidate and best_conf >= 0.15:
            validation = validate_plate(best_candidate)
            fmt_str = "PASS" if validation.is_valid else (
                "PARTIAL" if validation.format_confidence >= 0.3 else "FAIL"
            )
            return {
                "plate": best_candidate,
                "confidence": float(best_conf),
                "ocr_confidence": float(best_conf),
                "plate_detection_confidence": float(plate_det_confidence),
                "quality_score": float(quality.overall),
                "format_validation": fmt_str,
                "detection_method": det_method + "+easyocr",
                "vahan": VAHAN_DATABASE.get(best_candidate, self._default_vahan(best_candidate)),
                "_needs_fusion": True,  # Flag: not format-validated, needs multi-frame consensus
            }

        # --- Stage 7: Gemini VLM Fallback (Tier 3) ---
        if allow_gemini_fallback:
            try:
                from core_ai.gemini_vlm import gemini_vlm
                if gemini_vlm.is_available():
                    # User requested to crop the number plate part and give that to Gemini
                    gemini_res = gemini_vlm.decode_license_plate(plate_crop)
                    if gemini_res and gemini_res.get("plate_number"):
                        p_num = re.sub(r'[^A-Za-z0-9]', '', str(gemini_res["plate_number"])).upper()
                        g_conf = float(gemini_res.get("confidence", 0.0))
                        validation = validate_plate(p_num)
                        if g_conf >= 0.75 and validation.is_valid:
                            return self._build_anpr_record_v2(
                                p_num, g_conf, plate_det_confidence,
                                quality.overall, validation, "gemini"
                            )
            except Exception:
                pass

        # Zero fake numbers: if unreadable, return None
        return None

    def _build_anpr_record_v2(self, plate_str, ocr_conf, plate_det_conf,
                               quality_score, validation, method):
        """Build ANPR result with separated confidence fields (v2 format)."""
        vahan_info = VAHAN_DATABASE.get(plate_str, self._default_vahan(plate_str))
        fmt_str = "PASS" if validation.is_valid else (
            "PARTIAL" if validation.format_confidence >= 0.3 else "FAIL"
        )
        return {
            "plate": plate_str,
            "confidence": float(ocr_conf),  # backward-compatible
            "ocr_confidence": float(ocr_conf),
            "plate_detection_confidence": float(plate_det_conf),
            "quality_score": float(quality_score),
            "format_validation": fmt_str,
            "format_name": validation.format_name,
            "detection_method": method,
            "vahan": vahan_info,
        }
    @staticmethod
    def _default_vahan(plate_str):
        """Default VAHAN record for unregistered plates."""
        rto_code = plate_str[:4] if len(plate_str) >= 4 else "GJ"
        return {
            "owner": None,
            "make_model": None,
            "color": None,
            "rto": f"Gujarat RTO ({rto_code})",
            "status": "UNLISTED IN REGISTRY",
            "is_flagged": False,
            "fir_ref": None
        }

    # Keep legacy _build_anpr_record for any external callers
    def _build_anpr_record(self, plate_str: str, conf: float):
        vahan_info = VAHAN_DATABASE.get(plate_str)
        if not vahan_info:
            vahan_info = self._default_vahan(plate_str)
        return {
            "plate": plate_str,
            "confidence": float(conf),
            "vahan": vahan_info
        }