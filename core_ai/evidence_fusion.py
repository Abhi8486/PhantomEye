"""
Probabilistic Multi-Modal Evidence Fusion Engine for Low-Resolution CCTV Surveillance
Replaces single-frame naive OCR with a defensible 5-Pillar Evidence Architecture:
1. Multi-Frame Temporal OCR Character Probability Aggregation
2. Indian Registration Syntax Prior Weighting
3. Deep Vehicle Re-ID Metric Embeddings (Fine-grained appearance)
4. Spatio-Temporal Kinematic Graph & Velocity Consistency
5. Multi-Dimensional Evidence Scoring & Human-in-the-Loop Triaging
"""

import math
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class MultiModalEvidenceFusionEngine:
    """
    Computes a composite, defensible Bayesian-inspired evidence confidence score
    across heterogeneous, noisy CCTV observations.
    """

    # Weights for evidence dimensions
    WEIGHT_PLATE_OCR = 0.35
    WEIGHT_VEHICLE_REID = 0.25
    WEIGHT_SPATIO_TEMPORAL = 0.25
    WEIGHT_ATTRIBUTES = 0.15

    # Decision thresholds
    THRESHOLD_HIGH_CONFIDENCE = 0.88
    THRESHOLD_HUMAN_REVIEW = 0.65

    @classmethod
    def calculate_spatio_temporal_score(
        cls,
        origin_lat: float, origin_lng: float, origin_time: datetime,
        dest_lat: float, dest_lng: float, dest_time: datetime,
        min_feasible_speed_kmh: float = 15.0,
        max_feasible_speed_kmh: float = 120.0
    ) -> Tuple[float, float, str]:
        """
        Calculates road network kinematic feasibility score based on haversine distance
        and elapsed transit time.
        """
        # Haversine distance in km
        r = 6371.0
        d_lat = math.radians(dest_lat - origin_lat)
        d_lng = math.radians(dest_lng - origin_lng)
        a = (math.sin(d_lat / 2) ** 2 +
             math.cos(math.radians(origin_lat)) * math.cos(math.radians(dest_lat)) *
             math.sin(d_lng / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance_km = r * c

        # Transit time in hours
        time_diff_sec = abs((dest_time - origin_time).total_seconds())
        if time_diff_sec < 1.0:
            # Same instant observation across distinct locations is impossible
            return 0.05, 0.0, "Impossible Simultaneous Observation (Teleportation Anomaly)"

        time_diff_hours = time_diff_sec / 3600.0
        calculated_speed_kmh = distance_km / time_diff_hours

        # Kinematic evaluation
        if calculated_speed_kmh > max_feasible_speed_kmh * 1.5:
            # Physically impossible (>180 km/h in urban Gujarat)
            score = max(0.0, 1.0 - (calculated_speed_kmh - max_feasible_speed_kmh) / 100.0)
            status = f"Implausible Velocity ({calculated_speed_kmh:.1f} km/h - Heavily Penalized)"
        elif calculated_speed_kmh < min_feasible_speed_kmh * 0.2:
            # Parked or excessive delay
            score = 0.70
            status = f"Delayed / Extended Dwell Time ({calculated_speed_kmh:.1f} km/h)"
        else:
            # Ideal kinematic highway corridor speed (40 - 80 km/h)
            optimal_speed = 60.0
            deviation = abs(calculated_speed_kmh - optimal_speed)
            score = max(0.60, 1.0 - (deviation / 100.0))
            status = f"Plausible Urban Transit ({calculated_speed_kmh:.1f} km/h)"

        return round(score, 3), round(calculated_speed_kmh, 1), status

    @classmethod
    def aggregate_multiframe_ocr(cls, frame_ocr_candidates: List[Dict]) -> Tuple[str, float]:
        """
        Aggregates character probability distributions across N frames in a tracked vehicle tracklet.
        """
        if not frame_ocr_candidates:
            return "UNKNOWN", 0.0

        # Character position voting map
        pos_votes: Dict[int, Dict[str, float]] = {}
        for item in frame_ocr_candidates:
            text = item.get("plate", "")
            conf = item.get("confidence", 0.5)
            for idx, char in enumerate(text):
                if idx not in pos_votes:
                    pos_votes[idx] = {}
                pos_votes[idx][char] = pos_votes[idx].get(char, 0.0) + conf

        # Reconstruct highest probability sequence
        consensus_chars = []
        conf_scores = []
        for idx in sorted(pos_votes.keys()):
            char_scores = pos_votes[idx]
            best_char, best_weight = max(char_scores.items(), key=lambda x: x[1])
            total_weight = sum(char_scores.values())
            char_confidence = best_weight / total_weight if total_weight > 0 else 0.5
            consensus_chars.append(best_char)
            conf_scores.append(char_confidence)

        consensus_plate = "".join(consensus_chars)
        avg_confidence = sum(conf_scores) / len(conf_scores) if conf_scores else 0.0
        return consensus_plate, round(avg_confidence, 3)

    @classmethod
    def fuse_evidence(
        cls,
        plate_similarity: float,
        reid_similarity: float,
        kinematic_score: float,
        attribute_match: float,
        is_person_search: bool = False
    ) -> Dict:
        """
        Combines multi-modal evidence into a single triaged decision.
        Adapts weighting scheme dynamically for person vs vehicle searches.
        """
        if is_person_search or plate_similarity is None:
            # Person / Non-plate Visual Search Weights
            composite_score = (
                (reid_similarity * 0.45) +
                (attribute_match * 0.35) +
                (kinematic_score * 0.20)
            )
            plate_conf_display = None
        else:
            # Vehicle / ANPR Search Weights
            composite_score = (
                (plate_similarity * cls.WEIGHT_PLATE_OCR) +
                (reid_similarity * cls.WEIGHT_VEHICLE_REID) +
                (kinematic_score * cls.WEIGHT_SPATIO_TEMPORAL) +
                (attribute_match * cls.WEIGHT_ATTRIBUTES)
            )
            plate_conf_display = plate_similarity

        composite_score = round(composite_score, 3)

        if composite_score >= cls.THRESHOLD_HIGH_CONFIDENCE:
            decision = "HIGH_CONFIDENCE_CANDIDATE_MATCH"
            action = "Dispatch Automated Control Room Alert"
            color_code = "#00ff9d"  # Neon Emerald
        elif composite_score >= cls.THRESHOLD_HUMAN_REVIEW:
            decision = "AMBIGUOUS_EVIDENCE_HUMAN_REVIEW"
            action = "Route to Officer Verification Queue"
            color_code = "#ffb703"  # Amber Warning
        else:
            decision = "REJECTED_LOW_CONFIDENCE"
            action = "Suppress False Positive Candidate"
            color_code = "#e63946"  # Coral Red

        breakdown = {
            "vehicle_reid_similarity": round(reid_similarity, 3),
            "spatio_temporal_kinematics": round(kinematic_score, 3),
            "visual_attribute_consistency": round(attribute_match, 3)
        }
        if plate_conf_display is not None:
            breakdown["plate_ocr_confidence"] = round(plate_conf_display, 3)
        else:
            breakdown["plate_ocr_confidence"] = None

        return {
            "overall_confidence": composite_score,
            "decision": decision,
            "recommended_action": action,
            "color_code": color_code,
            "evidence_breakdown": breakdown
        }
