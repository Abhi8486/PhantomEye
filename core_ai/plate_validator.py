"""
Enhanced Indian Vehicle License Plate Format Validator
Position-aware character validation with state-code verification and format-specific rules.
Replaces the 3 inline regex patterns in anpr.py with comprehensive coverage.
"""

import re
from typing import Optional, Dict, Tuple

# All valid Indian state/UT codes (36 states and union territories)
VALID_STATE_CODES = frozenset({
    "AN",  # Andaman & Nicobar
    "AP",  # Andhra Pradesh
    "AR",  # Arunachal Pradesh
    "AS",  # Assam
    "BR",  # Bihar
    "CG",  # Chhattisgarh
    "CH",  # Chandigarh
    "DD",  # Daman & Diu / Dadra & Nagar Haveli
    "DL",  # Delhi
    "DN",  # Dadra & Nagar Haveli (legacy)
    "GA",  # Goa
    "GJ",  # Gujarat
    "HP",  # Himachal Pradesh
    "HR",  # Haryana
    "JH",  # Jharkhand
    "JK",  # Jammu & Kashmir
    "KA",  # Karnataka
    "KL",  # Kerala
    "LA",  # Ladakh
    "LD",  # Lakshadweep
    "MH",  # Maharashtra
    "ML",  # Meghalaya
    "MN",  # Manipur
    "MP",  # Madhya Pradesh
    "MZ",  # Mizoram
    "NL",  # Nagaland
    "OD",  # Odisha
    "OR",  # Odisha (legacy)
    "PB",  # Punjab
    "PY",  # Puducherry
    "RJ",  # Rajasthan
    "SK",  # Sikkim
    "TN",  # Tamil Nadu
    "TR",  # Tripura
    "TS",  # Telangana
    "UK",  # Uttarakhand
    "UP",  # Uttar Pradesh
    "UT",  # Uttarakhand (legacy)
    "WB",  # West Bengal
})

# Known valid RTO district numbers per state (partial, for common states)
# Format: state_code -> set of valid 2-digit RTO numbers
KNOWN_RTO_CODES: Dict[str, set] = {
    "GJ": set(range(1, 40)),   # Gujarat: GJ01 to GJ39
    "MH": set(range(1, 55)),   # Maharashtra
    "DL": set(range(1, 14)),   # Delhi
    "RJ": set(range(1, 55)),   # Rajasthan
    "KA": set(range(1, 75)),   # Karnataka
    "TN": set(range(1, 100)),  # Tamil Nadu
    "UP": set(range(1, 85)),   # Uttar Pradesh
    "HR": set(range(1, 80)),   # Haryana
    "PB": set(range(1, 75)),   # Punjab
    "AP": set(range(1, 40)),   # Andhra Pradesh
    "TS": set(range(1, 40)),   # Telangana
    "KL": set(range(1, 80)),   # Kerala
    "MP": set(range(1, 75)),   # Madhya Pradesh
    "CG": set(range(1, 30)),   # Chhattisgarh
    "WB": set(range(1, 90)),   # West Bengal
}

_STATES_PATTERN = '|'.join(sorted(VALID_STATE_CODES))


class PlateFormat:
    """Represents a detected Indian plate format with position rules."""
    def __init__(self, name: str, pattern: re.Pattern, position_types: str):
        """
        Args:
            name: Human-readable format name.
            pattern: Compiled regex for the full plate string.
            position_types: A string where each char indicates expected type:
                'A' = alpha, 'D' = digit, 'X' = either (alpha or digit).
                Example: "AADDAADDDD" for GJ01AB1234.
        """
        self.name = name
        self.pattern = pattern
        self.position_types = position_types


# All supported Indian plate formats
# IMPORTANT: Ordered from most specific to most general to prevent over-matching.
PLATE_FORMATS = [
    # Temporary registration: GJ01T1234 (state + RTO + 'T' + 4 digits)
    PlateFormat(
        "TEMPORARY",
        re.compile(rf'^({_STATES_PATTERN})[0-9]{{2}}T[0-9]{{4}}$'),
        "AADDADDDD"
    ),
    # Bharat Series: 22BH1234AA
    PlateFormat(
        "BHARAT_SERIES",
        re.compile(r'^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$'),
        "DDAADDDDAX"
    ),
    # Defence vehicles: 01A1234 (2 digits + 1 letter + 4 digits)
    PlateFormat(
        "DEFENCE",
        re.compile(r'^[0-9]{2}[A-Z][0-9]{4}$'),
        "DDADDDD"
    ),
    # Diplomatic vehicles: 84D1234
    PlateFormat(
        "DIPLOMATIC",
        re.compile(r'^[0-9]{2}D[0-9]{4}$'),
        "DDADDDD"
    ),
    # Standard Indian (post-2000): GJ01AB1234, GJ27AX9999, MH12DE1433, GJ01ABC1234
    # 2-3 letters + exactly 4 digits (total 10-11 chars). MUST come BEFORE Commercial.
    PlateFormat(
        "STANDARD_4DIGIT",
        re.compile(rf'^({_STATES_PATTERN})[0-9]{{2}}[A-Z]{{2,3}}[0-9]{{4}}$'),
        "AADDXXADDDD"
    ),
    # Commercial/Short: GJ27E5539, GJ01AW6670
    # 1 letter + 3-4 digits (total 8-9 chars)  — e.g., GJ27E5539
    # 2 letters + 3 digits (total 9 chars) — e.g., GJ27AW667
    # Catches plates that DIDN'T match Standard (which requires 2+ letters + exactly 4 digits)
    PlateFormat(
        "COMMERCIAL_SHORT",
        re.compile(rf'^({_STATES_PATTERN})[0-9]{{2}}[A-Z]{{1}}[0-9]{{3,4}}$'),
        "AADDADDDD"
    ),
    # Commercial with 2 letters + 3 digits: GJ01AW667 (rare but valid)
    PlateFormat(
        "COMMERCIAL_2L3D",
        re.compile(rf'^({_STATES_PATTERN})[0-9]{{2}}[A-Z]{{2}}[0-9]{{3}}$'),
        "AADDAADDD"
    ),
    # EV Green plates follow standard format, just different color
    # They use the same alphanumeric format, detected via color in plate_detector
]


class PlateValidationResult:
    """Result of plate format validation."""
    __slots__ = (
        "is_valid", "format_name", "format_confidence",
        "state_code", "rto_code", "rto_valid",
        "corrected_text", "issues"
    )

    def __init__(self):
        self.is_valid: bool = False
        self.format_name: Optional[str] = None
        self.format_confidence: float = 0.0
        self.state_code: Optional[str] = None
        self.rto_code: Optional[int] = None
        self.rto_valid: Optional[bool] = None
        self.corrected_text: Optional[str] = None
        self.issues: list = []

    def to_dict(self) -> Dict:
        return {
            "is_valid": self.is_valid,
            "format_name": self.format_name,
            "format_confidence": self.format_confidence,
            "state_code": self.state_code,
            "rto_code": self.rto_code,
            "rto_valid": self.rto_valid,
            "corrected_text": self.corrected_text,
            "issues": self.issues,
        }


def validate_plate(text: str) -> PlateValidationResult:
    """
    Validates a cleaned alphanumeric string against all known Indian plate formats.
    Returns a PlateValidationResult with match details and confidence.
    
    Args:
        text: Cleaned uppercase alphanumeric plate string (no spaces/dashes).
    
    Returns:
        PlateValidationResult with is_valid, format_name, confidence, etc.
    """
    result = PlateValidationResult()

    if not text or len(text) < 6 or len(text) > 13:
        result.issues.append(f"Invalid length: {len(text) if text else 0}")
        return result

    text = text.upper().strip()

    # Try each format
    for fmt in PLATE_FORMATS:
        if fmt.pattern.fullmatch(text):
            result.is_valid = True
            result.format_name = fmt.name
            result.format_confidence = 1.0

            # Extract and validate state code for non-Bharat/Defence/Diplomatic
            if fmt.name not in ("BHARAT_SERIES", "DEFENCE", "DIPLOMATIC"):
                state = text[:2]
                result.state_code = state
                if state in VALID_STATE_CODES:
                    result.format_confidence = 1.0
                else:
                    result.format_confidence = 0.5
                    result.issues.append(f"Unknown state code: {state}")

                # Validate RTO district number
                try:
                    rto_num = int(text[2:4])
                    result.rto_code = rto_num
                    if state in KNOWN_RTO_CODES:
                        if rto_num in KNOWN_RTO_CODES[state]:
                            result.rto_valid = True
                        else:
                            result.rto_valid = False
                            result.format_confidence = max(0.7, result.format_confidence - 0.1)
                            result.issues.append(f"Unknown RTO code {rto_num} for {state}")
                    else:
                        # State exists but we don't have its RTO list — assume valid
                        result.rto_valid = None
                except ValueError:
                    result.issues.append("Invalid RTO digit")
                    result.format_confidence = 0.6

            elif fmt.name == "BHARAT_SERIES":
                # Validate year prefix (19-29 for BH series introduced in 2021)
                try:
                    year = int(text[:2])
                    if 19 <= year <= 35:
                        result.format_confidence = 1.0
                    else:
                        result.format_confidence = 0.6
                        result.issues.append(f"Unusual BH year prefix: {year}")
                except ValueError:
                    result.format_confidence = 0.5

            result.corrected_text = text
            return result

    # No exact match — check for partial/near-match
    # Try to detect if it looks like a state-RTO prefix at least
    if len(text) >= 4 and text[:2].isalpha() and text[2:4].isdigit():
        state = text[:2]
        if state in VALID_STATE_CODES:
            result.state_code = state
            result.format_confidence = 0.3
            result.issues.append("Partial match: valid state code but format doesn't match known patterns")
        else:
            result.format_confidence = 0.1
            result.issues.append("No format match and unknown state prefix")
    else:
        result.format_confidence = 0.0
        result.issues.append("Does not match any known Indian plate format")

    return result


def get_position_types(text: str) -> Optional[str]:
    """
    Returns a position-type string for a matched plate format.
    Each char is 'A' (expected alpha), 'D' (expected digit), or 'X' (either).
    Returns None if the text doesn't match any format.
    
    This is used by the OCR error correction module to know which positions
    should be letters vs digits.
    """
    text = text.upper().strip()

    # Standard: SS DD LLL DDDD (state, rto, letters, digits)
    # e.g., GJ01AB1234 → AADDAADDDD (10 chars)
    # e.g., GJ01ABC1234 → AADDAAADDDD (11 chars)
    for fmt in PLATE_FORMATS:
        if fmt.pattern.fullmatch(text):
            if fmt.name == "STANDARD_4DIGIT":
                # Positions 0-1: alpha, 2-3: digit, then letters until last 4, last 4: digits
                types = ['A', 'A', 'D', 'D']
                remaining = text[4:]
                letters_end = 0
                for i, ch in enumerate(remaining):
                    if ch.isdigit():
                        letters_end = i
                        break
                    types.append('A')
                for ch in remaining[letters_end:]:
                    types.append('D')
                return ''.join(types)

            elif fmt.name == "COMMERCIAL_SHORT":
                types = ['A', 'A', 'D', 'D']
                remaining = text[4:]
                for i, ch in enumerate(remaining):
                    if ch.isdigit():
                        types.extend(['D'] * len(remaining[i:]))
                        break
                    types.append('A')
                return ''.join(types)

            elif fmt.name == "BHARAT_SERIES":
                # DD BH DDDD AA
                types = ['D', 'D', 'A', 'A']  # year + BH
                types.extend(['D', 'D', 'D', 'D'])  # 4 digits
                for ch in text[8:]:
                    types.append('A')
                return ''.join(types)

            elif fmt.name == "TEMPORARY":
                return 'A' * 2 + 'D' * 2 + 'A' + 'D' * 4

            elif fmt.name in ("DEFENCE", "DIPLOMATIC"):
                return 'D' * 2 + 'A' + 'D' * 4

    return None
