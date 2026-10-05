"""
High-Speed Multi-Object Tracker (IoU + Centroid Matching)
Maintains unique track IDs across frames with zero ghost trails.

v2: Added centroid history, first/last seen timestamps for direction,
    trajectory, dwell time, and speed analytics.
"""

import time
import numpy as np
from collections import deque

# Maximum centroid history entries per track (ring buffer)
MAX_CENTROID_HISTORY = 30


class ZeroTrailTracker:
    def __init__(self, max_missed=15):
        self.tracks = {}
        self.next_id = 1
        self.max_missed = max_missed
        self._frame_count = 0

    def update(self, detections):
        self._frame_count += 1
        now_t = time.time()
        updated = {}
        unmatched = list(detections)

        for tid, track in list(self.tracks.items()):
            tx1, ty1, tx2, ty2 = track["box"]
            tcx, tcy = (tx1 + tx2) / 2.0, (ty1 + ty2) / 2.0

            best_score = -999.0
            best_idx = -1

            for idx, det in enumerate(unmatched):
                if det["label"] == track["label"]:
                    dx1, dy1, dx2, dy2 = det["box"]
                    dcx, dcy = (dx1 + dx2) / 2.0, (dy1 + dy2) / 2.0

                    # Calculate IoU
                    xx1, yy1 = max(tx1, dx1), max(ty1, dy1)
                    xx2, yy2 = min(tx2, dx2), min(ty2, dy2)
                    inter = max(0, xx2 - xx1) * max(0, yy2 - yy1)
                    area_t = (tx2 - tx1) * (ty2 - ty1)
                    area_d = (dx2 - dx1) * (dy2 - dy1)
                    union = area_t + area_d - inter
                    iou = inter / max(1.0, union)

                    # Distance penalty
                    dist = np.hypot(dcx - tcx, dcy - tcy)
                    score = iou - (dist / 800.0)

                    if score > best_score:
                        best_score = score
                        best_idx = idx

            # Lowered score threshold from 0.15 to -0.2 to allow fast-moving vehicles
            # with 0 IoU to still match if they are close in distance.
            if best_score > -0.20 and best_idx >= 0:
                matched = unmatched.pop(best_idx)
                sx1 = int(0.75 * matched["box"][0] + 0.25 * tx1)
                sy1 = int(0.75 * matched["box"][1] + 0.25 * ty1)
                sx2 = int(0.75 * matched["box"][2] + 0.25 * tx2)
                sy2 = int(0.75 * matched["box"][3] + 0.25 * ty2)

                # Carry forward centroid history and timestamps
                centroid_history = track.get("centroid_history", deque(maxlen=MAX_CENTROID_HISTORY))
                new_cx = (sx1 + sx2) / 2.0
                new_cy = (sy1 + sy2) / 2.0
                centroid_history.append((new_cx, new_cy, now_t))

                updated[tid] = {
                    "track_id": tid,
                    "box": (sx1, sy1, sx2, sy2),
                    "label": matched["label"],
                    "class_name": matched["class_name"],
                    "confidence": matched["confidence"],
                    "is_threat": matched["is_threat"],
                    "is_vehicle": matched["is_vehicle"],
                    "is_person": matched["is_person"],
                    "missed": 0,
                    "plate_info": track.get("plate_info") or matched.get("plate_info"),
                    # v2 fields
                    "centroid_history": centroid_history,
                    "first_seen_time": track.get("first_seen_time", now_t),
                    "last_seen_time": now_t,
                    "first_seen_frame": track.get("first_seen_frame", self._frame_count),
                    "last_seen_frame": self._frame_count,
                }
            else:
                if track["missed"] < self.max_missed:
                    track["missed"] += 1
                    track["last_seen_time"] = now_t
                    track["last_seen_frame"] = self._frame_count
                    updated[tid] = track

        for det in unmatched:
            cx = (det["box"][0] + det["box"][2]) / 2.0
            cy = (det["box"][1] + det["box"][3]) / 2.0
            history = deque(maxlen=MAX_CENTROID_HISTORY)
            history.append((cx, cy, now_t))

            updated[self.next_id] = {
                "track_id": self.next_id,
                "box": det["box"],
                "label": det["label"],
                "class_name": det["class_name"],
                "confidence": det["confidence"],
                "is_threat": det["is_threat"],
                "is_vehicle": det["is_vehicle"],
                "is_person": det["is_person"],
                "missed": 0,
                "plate_info": det.get("plate_info"),
                # v2 fields
                "centroid_history": history,
                "first_seen_time": now_t,
                "last_seen_time": now_t,
                "first_seen_frame": self._frame_count,
                "last_seen_frame": self._frame_count,
            }
            self.next_id += 1

        self.tracks = updated
        return self.tracks

