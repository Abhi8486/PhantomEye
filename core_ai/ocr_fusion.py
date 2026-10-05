"""
Multi-Frame OCR Fusion Engine — Accumulates OCR readings per tracked vehicle,
applies position-aware error correction, and confirms plates via consensus.

Uses the existing evidence_fusion.py aggregate_multiframe_ocr for character-level voting
to avoid code duplication.
"""

import re
import time
from typing import Optional, Dict, List, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

from core_ai.plate_validator import validate_plate, get_position_types


# Position-aware OCR error correction maps
# Used ONLY when the character position's expected type is known from format analysis
_DIGIT_CORRECTIONS = {
    'O': '0', 'o': '0',
    'I': '1', 'i': '1', 'l': '1', 'L': '1',
    'B': '8',
    'S': '5', 's': '5',
    'Z': '2', 'z': '2',
    'G': '6', 'g': '6',
    'T': '7',
    'A': '4',
    'D': '0',
}

_LETTER_CORRECTIONS = {
    '0': 'O',
    '1': 'I',
    '8': 'B',
    '5': 'S',
    '2': 'Z',
    '6': 'G',
}


@dataclass
class OCRReading:
    """A single-frame OCR reading for a tracked vehicle."""
    text: str               # Raw cleaned OCR text
    corrected_text: str      # After position-aware error correction
    ocr_confidence: float    # EasyOCR confidence
    quality_score: float     # Plate image quality score
    frame_num: int           # Frame number when this reading was taken
    timestamp: float         # Unix timestamp
    detection_method: str    # "yolo+easyocr", "hsv+easyocr", "gemini"


@dataclass
class ConfirmedPlate:
    """A confirmed plate number after multi-frame consensus."""
    plate_text: str
    best_ocr_confidence: float
    best_quality_score: float
    agreement_ratio: float       # What fraction of readings agree
    agreement_count: int         # How many readings agree
    total_readings: int          # Total readings attempted
    format_validation: str       # "PASS" / "PARTIAL" / "FAIL"
    format_name: Optional[str]
    detection_method: str        # Method of the best reading
    final_confidence: float      # Composite confidence score
    confirmed_at: float          # Unix timestamp


# Configuration
MAX_HISTORY_PER_VEHICLE = 10     # Max OCR readings to keep per vehicle
MIN_READINGS_FOR_CONFIRM = 2     # Minimum readings needed for confirmation
MIN_AGREEMENT_RATIO = 0.60       # 60% of readings must agree
COOLDOWN_AFTER_CONFIRM_SEC = 30  # Skip OCR for 30s after confirmation
STALE_VEHICLE_TIMEOUT_SEC = 60   # Remove history for vehicles not seen in 60s


class OCRFusionEngine:
    """
    Manages per-vehicle OCR history, applies error correction, and confirms
    plates via multi-frame consensus voting.
    """

    def __init__(self):
        # track_id -> list of OCRReading
        self._history: Dict[int, List[OCRReading]] = {}
        # track_id -> ConfirmedPlate
        self._confirmed: Dict[int, ConfirmedPlate] = {}
        # track_id -> last activity timestamp
        self._last_seen: Dict[int, float] = {}

    def should_skip_ocr(self, track_id: int) -> bool:
        """
        Check if OCR should be skipped for this vehicle.
        Returns True if the vehicle already has a confirmed plate and is in cooldown.
        """
        if track_id in self._confirmed:
            elapsed = time.time() - self._confirmed[track_id].confirmed_at
            if elapsed < COOLDOWN_AFTER_CONFIRM_SEC:
                return True
        return False

    def add_reading(self, track_id: int, text: str, ocr_confidence: float,
                    quality_score: float, frame_num: int,
                    detection_method: str = "unknown") -> Optional[ConfirmedPlate]:
        """
        Add a single-frame OCR reading for a tracked vehicle.
        Applies error correction and checks for consensus.

        Args:
            track_id: Tracker ID for this vehicle.
            text: Raw cleaned OCR text (alphanumeric, uppercase).
            ocr_confidence: Confidence from EasyOCR (0-1).
            quality_score: Image quality score (0-1).
            frame_num: Current frame number.
            detection_method: Detection method string.

        Returns:
            ConfirmedPlate if consensus is reached on this reading, else None.
        """
        if not text or len(text) < 6:
            return None

        text = re.sub(r'[^A-Za-z0-9]', '', text).upper()
        if len(text) < 6:
            return None

        # Apply position-aware error correction
        corrected = self._apply_error_correction(text)

        now = time.time()
        reading = OCRReading(
            text=text,
            corrected_text=corrected,
            ocr_confidence=ocr_confidence,
            quality_score=quality_score,
            frame_num=frame_num,
            timestamp=now,
            detection_method=detection_method,
        )

        # Initialize or append to history
        if track_id not in self._history:
            self._history[track_id] = []

        history = self._history[track_id]
        history.append(reading)

        # Bound history size
        if len(history) > MAX_HISTORY_PER_VEHICLE:
            history.pop(0)

        self._last_seen[track_id] = now

        # Check for consensus
        confirmed = self._check_consensus(track_id)
        if confirmed:
            self._confirmed[track_id] = confirmed
        return confirmed

    def get_confirmed_plate(self, track_id: int) -> Optional[ConfirmedPlate]:
        """Returns confirmed plate for a track_id, or None."""
        return self._confirmed.get(track_id)

    def cleanup_stale(self, active_track_ids: Set[int]):
        """
        Remove history and confirmations for vehicles that are no longer tracked.
        Called periodically from the video stream worker.
        """
        now = time.time()
        stale_ids = []

        for tid in list(self._history.keys()):
            if tid not in active_track_ids:
                last_seen = self._last_seen.get(tid, 0)
                if now - last_seen > STALE_VEHICLE_TIMEOUT_SEC:
                    stale_ids.append(tid)

        for tid in stale_ids:
            self._history.pop(tid, None)
            self._confirmed.pop(tid, None)
            self._last_seen.pop(tid, None)

    def get_history_count(self, track_id: int) -> int:
        """Returns the number of OCR readings stored for a track_id."""
        return len(self._history.get(track_id, []))

    def _apply_error_correction(self, text: str) -> str:
        """
        Apply position-aware OCR error correction.
        Uses the plate format validator to determine expected character types at each position.
        Only corrects characters when the format is known — does NOT blindly substitute.
        """
        # First, try to validate the raw text to detect its format
        validation = validate_plate(text)
        position_types = get_position_types(text)

        if position_types and len(position_types) == len(text):
            # We know the expected type at each position — apply corrections
            corrected_chars = list(text)
            for i, (ch, expected) in enumerate(zip(text, position_types)):
                if expected == 'D' and ch.isalpha():
                    # Expected digit but got letter
                    corrected_chars[i] = _DIGIT_CORRECTIONS.get(ch, ch)
                elif expected == 'A' and ch.isdigit():
                    # Expected letter but got digit
                    corrected_chars[i] = _LETTER_CORRECTIONS.get(ch, ch)
                # 'X' = either — no correction
            corrected = ''.join(corrected_chars)

            # Verify the correction actually improved things
            corrected_validation = validate_plate(corrected)
            if corrected_validation.format_confidence >= validation.format_confidence:
                return corrected

        # If we couldn't determine position types, try a brute-force approach:
        # Only correct if the result matches a known format and the original doesn't
        if not validation.is_valid:
            # Try common single-character corrections
            for i, ch in enumerate(text):
                candidates = []
                if ch in _DIGIT_CORRECTIONS:
                    trial = text[:i] + _DIGIT_CORRECTIONS[ch] + text[i+1:]
                    trial_val = validate_plate(trial)
                    if trial_val.is_valid:
                        candidates.append((trial, trial_val.format_confidence))
                if ch in _LETTER_CORRECTIONS:
                    trial = text[:i] + _LETTER_CORRECTIONS[ch] + text[i+1:]
                    trial_val = validate_plate(trial)
                    if trial_val.is_valid:
                        candidates.append((trial, trial_val.format_confidence))
                if candidates:
                    # Take the correction with highest confidence
                    best = max(candidates, key=lambda x: x[1])
                    # Only accept if it results in a valid plate
                    if best[1] >= 0.7:
                        return best[0]

        return text  # No correction applied

    def _check_consensus(self, track_id: int) -> Optional[ConfirmedPlate]:
        """
        Check if there's enough agreement among readings to confirm a plate.

        Logic:
        1. Group readings by corrected_text.
        2. The largest group must have >= MIN_READINGS_FOR_CONFIRM readings.
        3. The largest group must represent >= MIN_AGREEMENT_RATIO of total readings.
        4. The best reading (highest ocr_conf * quality_score) in the group is used.
        """
        history = self._history.get(track_id, [])
        if not history:
            return None

        # Group by corrected text
        groups: Dict[str, List[OCRReading]] = defaultdict(list)
        for reading in history:
            groups[reading.corrected_text].append(reading)

        if not groups:
            return None

        # Find the largest group
        best_text = max(groups, key=lambda k: len(groups[k]))
        best_group = groups[best_text]
        total = len(history)
        agreement_count = len(best_group)
        agreement_ratio = agreement_count / total

        # Validate the plate format early to determine required readings
        validation = validate_plate(best_text)
        is_perfect = validation.is_valid and validation.format_confidence == 1.0
        
        required_readings = 1 if is_perfect else MIN_READINGS_FOR_CONFIRM

        # Check thresholds
        if agreement_count < required_readings:
            return None
        if agreement_ratio < MIN_AGREEMENT_RATIO:
            return None

        # Find the best reading within the winning group
        best_reading = max(best_group,
                           key=lambda r: r.ocr_confidence * r.quality_score)

        # Validate the plate format (already done above)
        if validation.is_valid:
            format_validation = "PASS"
        elif validation.format_confidence >= 0.3:
            format_validation = "PARTIAL"
        else:
            return None  # Completely invalid format, reject consensus

        # Calculate final composite confidence
        final_confidence = self._calculate_final_confidence(
            agreement_ratio=agreement_ratio,
            best_ocr_confidence=best_reading.ocr_confidence,
            plate_detection_confidence=best_reading.quality_score,  # proxy
            quality_score=best_reading.quality_score,
            format_valid=(format_validation == "PASS"),
        )

        return ConfirmedPlate(
            plate_text=best_text,
            best_ocr_confidence=best_reading.ocr_confidence,
            best_quality_score=best_reading.quality_score,
            agreement_ratio=round(agreement_ratio, 3),
            agreement_count=agreement_count,
            total_readings=total,
            format_validation=format_validation,
            format_name=validation.format_name,
            detection_method=best_reading.detection_method,
            final_confidence=final_confidence,
            confirmed_at=time.time(),
        )

    @staticmethod
    def _calculate_final_confidence(
        agreement_ratio: float,
        best_ocr_confidence: float,
        plate_detection_confidence: float,
        quality_score: float,
        format_valid: bool,
    ) -> float:
        """
        Composite confidence score — NOT a simple average.

        Weights:
          0.30 × multi_frame_agreement  — strongest signal (consistent across frames)
          0.25 × best_ocr_confidence    — best single-frame OCR reading
          0.20 × plate_detection_conf   — how reliably the plate was localized
          0.15 × quality_score          — image quality of the best crop
          0.10 × format_validation      — 1.0 if valid Indian format, 0.0 if not
        """
        format_score = 1.0 if format_valid else 0.0

        composite = (
            0.30 * agreement_ratio +
            0.25 * best_ocr_confidence +
            0.20 * plate_detection_confidence +
            0.15 * quality_score +
            0.10 * format_score
        )
        return round(min(1.0, max(0.0, composite)), 3)


# Global singleton instance
ocr_fusion = OCRFusionEngine()
