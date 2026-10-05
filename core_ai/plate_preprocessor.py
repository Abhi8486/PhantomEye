"""
Plate Preprocessing Pipeline — Perspective Correction, Quality Scoring & Image Enhancement.
Replaces inline _preprocess_crop logic from anpr.py with a proper multi-stage pipeline.
All operations are CPU-safe (OpenCV + NumPy only).
"""

import cv2
import numpy as np
import math
from typing import Optional, Tuple, Dict


class PlateQualityScore:
    """Quality assessment result for a plate crop."""
    __slots__ = (
        "overall", "sharpness", "brightness", "contrast",
        "size_score", "tilt_angle", "tilt_score", "det_confidence"
    )

    def __init__(self):
        self.overall: float = 0.0
        self.sharpness: float = 0.0
        self.brightness: float = 0.0
        self.contrast: float = 0.0
        self.size_score: float = 0.0
        self.tilt_angle: float = 0.0
        self.tilt_score: float = 0.0
        self.det_confidence: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "overall": round(self.overall, 3),
            "sharpness": round(self.sharpness, 3),
            "brightness": round(self.brightness, 3),
            "contrast": round(self.contrast, 3),
            "size_score": round(self.size_score, 3),
            "tilt_angle": round(self.tilt_angle, 1),
            "tilt_score": round(self.tilt_score, 3),
            "det_confidence": round(self.det_confidence, 3),
        }


# Quality gate threshold — below this, skip OCR and wait for a better frame
QUALITY_GATE_THRESHOLD = 0.25


def score_quality(plate_crop: np.ndarray, detection_confidence: float = 0.5) -> PlateQualityScore:
    """
    Compute a quality score for a plate crop to decide whether OCR is worthwhile.

    Quality Score (0.0–1.0) = weighted combination of:
      - Sharpness (Laplacian variance): detects blur/motion blur
      - Brightness (mean intensity): detects under/over exposure
      - Contrast (std dev of grayscale): detects washed-out plates
      - Size (plate area in pixels): too small = unreliable
      - Tilt (estimated rotation angle): highly tilted plates are harder to read
      - Detection confidence: passed through from the plate detector

    Args:
        plate_crop: BGR image of the detected plate region.
        detection_confidence: Confidence from the plate detector (0-1).

    Returns:
        PlateQualityScore with individual and overall scores.
    """
    result = PlateQualityScore()
    result.det_confidence = detection_confidence

    if plate_crop is None or plate_crop.size == 0:
        return result

    h, w = plate_crop.shape[:2]
    if h < 5 or w < 5:
        return result

    gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY) if len(plate_crop.shape) == 3 else plate_crop

    # 1. Sharpness — Laplacian variance
    # High variance = sharp edges = readable text
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    lap_var = laplacian.var()
    # Normalize: <50 is very blurry, >500 is very sharp
    result.sharpness = min(1.0, max(0.0, (lap_var - 20.0) / 480.0))

    # 2. Brightness — Mean pixel intensity
    # Ideal range: 80-200 (not too dark, not too bright)
    mean_val = float(np.mean(gray))
    if mean_val < 40:
        result.brightness = mean_val / 40.0 * 0.3  # Very dark
    elif mean_val > 230:
        result.brightness = max(0.0, 1.0 - (mean_val - 230) / 25.0) * 0.5  # Washed out
    elif 80 <= mean_val <= 200:
        result.brightness = 1.0  # Ideal range
    elif mean_val < 80:
        result.brightness = 0.5 + 0.5 * (mean_val - 40) / 40.0  # Dim but usable
    else:  # 200-230
        result.brightness = 0.7 + 0.3 * (230 - mean_val) / 30.0  # Bright but ok

    # 3. Contrast — Std deviation of pixel intensities
    # High std dev = good contrast between text and background
    std_val = float(np.std(gray))
    # Normalize: <15 is very low contrast, >60 is excellent
    result.contrast = min(1.0, max(0.0, (std_val - 10.0) / 50.0))

    # 4. Size — Plate area in pixels
    # Minimum readable plate: ~40x15 pixels
    # Ideal: >100x30 pixels
    area = w * h
    if area < 200:
        result.size_score = 0.1  # Too small
    elif area < 600:
        result.size_score = 0.3 + 0.4 * (area - 200) / 400.0
    elif area < 3000:
        result.size_score = 0.7 + 0.3 * (area - 600) / 2400.0
    else:
        result.size_score = 1.0  # Large enough

    # 5. Tilt — Estimated rotation angle
    result.tilt_angle = _estimate_tilt_angle(gray)
    # 0 degrees = perfect, >30 degrees = very tilted
    abs_tilt = abs(result.tilt_angle)
    if abs_tilt < 5:
        result.tilt_score = 1.0
    elif abs_tilt < 15:
        result.tilt_score = 0.7 + 0.3 * (15 - abs_tilt) / 10.0
    elif abs_tilt < 30:
        result.tilt_score = 0.3 + 0.4 * (30 - abs_tilt) / 15.0
    else:
        result.tilt_score = max(0.1, 0.3 * (45 - abs_tilt) / 15.0)

    # Weighted overall score
    result.overall = (
        0.30 * result.sharpness +
        0.20 * result.brightness +
        0.20 * result.contrast +
        0.15 * result.size_score +
        0.10 * result.tilt_score +
        0.05 * result.det_confidence
    )

    return result


def _estimate_tilt_angle(gray: np.ndarray) -> float:
    """
    Estimate the tilt angle of text in a plate crop using Hough line detection.
    Returns angle in degrees (-45 to 45). 0 means horizontal text.
    """
    try:
        # Edge detection
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)

        # Hough line detection
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=30,
                                minLineLength=max(15, gray.shape[1] // 4),
                                maxLineGap=10)

        if lines is None or len(lines) == 0:
            return 0.0

        # Calculate angles of detected lines
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 - x1 == 0:
                continue
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            # Only consider near-horizontal lines (plate edges, text baselines)
            if abs(angle) < 45:
                angles.append(angle)

        if not angles:
            return 0.0

        # Median angle (robust to outliers)
        return float(np.median(angles))

    except Exception:
        return 0.0


def correct_perspective(plate_crop: np.ndarray) -> Tuple[np.ndarray, bool]:
    """
    Attempt perspective correction on a plate crop.

    Tries to find a quadrilateral boundary of the plate and warp it to a rectangle.
    Falls back to the original crop if four reliable corners cannot be found.

    Args:
        plate_crop: BGR image of the detected plate region.

    Returns:
        Tuple of (corrected_crop, was_corrected).
        was_corrected is True if perspective transformation was applied.
    """
    if plate_crop is None or plate_crop.size == 0:
        return plate_crop, False

    h, w = plate_crop.shape[:2]
    if h < 15 or w < 20:
        return plate_crop, False

    try:
        gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY) if len(plate_crop.shape) == 3 else plate_crop

        # Enhance edges
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 30, 120)

        # Dilate to connect broken edges
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.dilate(edges, kernel, iterations=1)

        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return plate_crop, False

        # Sort by area, largest first
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        for cnt in contours[:5]:  # Check top 5 largest contours
            # Approximate to polygon
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)

            # We need exactly 4 corners for perspective transform
            if len(approx) == 4:
                pts = approx.reshape(4, 2).astype(np.float32)

                # Validate the quadrilateral is reasonable
                if _is_valid_quadrilateral(pts, w, h):
                    # Order points: top-left, top-right, bottom-right, bottom-left
                    ordered = _order_points(pts)

                    # Calculate output dimensions
                    width_top = np.linalg.norm(ordered[1] - ordered[0])
                    width_bottom = np.linalg.norm(ordered[2] - ordered[3])
                    out_w = int(max(width_top, width_bottom))

                    height_left = np.linalg.norm(ordered[3] - ordered[0])
                    height_right = np.linalg.norm(ordered[2] - ordered[1])
                    out_h = int(max(height_left, height_right))

                    if out_w < 20 or out_h < 10:
                        continue

                    # Perspective transform
                    dst_pts = np.array([
                        [0, 0],
                        [out_w - 1, 0],
                        [out_w - 1, out_h - 1],
                        [0, out_h - 1]
                    ], dtype=np.float32)

                    M = cv2.getPerspectiveTransform(ordered, dst_pts)
                    warped = cv2.warpPerspective(plate_crop, M, (out_w, out_h))

                    if warped.size > 0:
                        return warped, True

        # No valid quadrilateral found — check if simple rotation would help
        tilt = _estimate_tilt_angle(gray)
        if abs(tilt) > 5:
            # Apply simple rotation correction
            center = (w // 2, h // 2)
            M_rot = cv2.getRotationMatrix2D(center, tilt, 1.0)
            rotated = cv2.warpAffine(plate_crop, M_rot, (w, h),
                                     flags=cv2.INTER_LINEAR,
                                     borderMode=cv2.BORDER_REPLICATE)
            return rotated, True

    except Exception as e:
        print(f"[PLATE_PREPROCESS] Perspective correction error: {e}")

    return plate_crop, False


def _is_valid_quadrilateral(pts: np.ndarray, img_w: int, img_h: int) -> bool:
    """
    Validate that a 4-point polygon is a reasonable plate boundary.
    Checks area, aspect ratio, and convexity.
    """
    try:
        # Check area is a reasonable fraction of the image
        area = cv2.contourArea(pts.astype(np.int32))
        img_area = img_w * img_h
        area_ratio = area / img_area
        if area_ratio < 0.15 or area_ratio > 0.98:
            return False

        # Check convexity
        hull = cv2.convexHull(pts.astype(np.int32))
        if len(hull) != 4:
            return False

        # Check that no point is outside the image (with small margin)
        margin = 5
        for pt in pts:
            if pt[0] < -margin or pt[0] > img_w + margin:
                return False
            if pt[1] < -margin or pt[1] > img_h + margin:
                return False

        return True
    except Exception:
        return False


def _order_points(pts: np.ndarray) -> np.ndarray:
    """
    Order 4 points as: top-left, top-right, bottom-right, bottom-left.
    """
    rect = np.zeros((4, 2), dtype=np.float32)

    # Sum: top-left has smallest sum, bottom-right has largest
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    # Diff: top-right has smallest diff, bottom-left has largest
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]

    return rect


def enhance_plate(plate_crop: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Apply image enhancement to a plate crop for optimal OCR readability.
    Uses CLAHE contrast enhancement + Laplacian sharpening (same as original anpr.py logic).

    Args:
        plate_crop: BGR image of the plate (after detection and optional perspective correction).

    Returns:
        Tuple of (enhanced_grayscale_for_ocr, raw_plate_bgr_upscaled).
    """
    if plate_crop is None or plate_crop.size == 0:
        return plate_crop, plate_crop

    ph, pw = plate_crop.shape[:2]

    # Upscale with Lanczos for super-resolution clarity
    scale = max(2, int(160 / max(pw, 1)))
    # Cap scale to avoid excessive memory usage
    scale = min(scale, 6)
    upscaled = cv2.resize(plate_crop, (pw * scale, ph * scale), interpolation=cv2.INTER_LANCZOS4)

    # CLAHE Contrast Enhancement
    gray_upscaled = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY) if len(upscaled.shape) == 3 else upscaled
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray_upscaled)

    # Laplacian sharpening (same as original anpr.py)
    laplacian = cv2.Laplacian(enhanced, cv2.CV_64F)
    sharpened = cv2.convertScaleAbs(enhanced - 0.5 * laplacian)

    return sharpened, upscaled
