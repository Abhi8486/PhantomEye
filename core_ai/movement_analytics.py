"""
Vehicle Movement Analytics — Direction, Trajectory, Dwell Time & Speed Estimation.
Computes movement metrics from the tracker's centroid history (ring buffer of positions).

All operations are pure NumPy math — zero model cost, <0.1ms per vehicle.
"""

import math
import numpy as np
from typing import Optional, Dict, List, Tuple
from collections import deque


# Cardinal direction names
_DIRECTIONS = {
    (0, -1): "N", (0, 1): "S", (1, 0): "E", (-1, 0): "W",
    (1, -1): "NE", (-1, -1): "NW", (1, 1): "SE", (-1, 1): "SW",
}


def estimate_direction(centroid_history: deque) -> Optional[str]:
    """
    Estimate dominant direction of travel from centroid history.
    Uses first-to-last vector for robustness against noise.

    Args:
        centroid_history: deque of (cx, cy, timestamp) tuples.

    Returns:
        Cardinal direction string (N, S, E, W, NE, NW, SE, SW) or None if insufficient data.
    """
    if not centroid_history or len(centroid_history) < 3:
        return None

    first = centroid_history[0]
    last = centroid_history[-1]
    dx = last[0] - first[0]
    dy = last[1] - first[1]

    # Ignore very small movements (parked/stationary)
    magnitude = math.hypot(dx, dy)
    if magnitude < 10.0:
        return "STATIONARY"

    # Map to cardinal direction
    angle = math.degrees(math.atan2(dy, dx))
    # atan2 gives angle from positive X-axis. Convert to compass:
    # Right = East, Down = South (in image coordinates, y increases downward)
    if -22.5 <= angle < 22.5:
        return "E"
    elif 22.5 <= angle < 67.5:
        return "SE"
    elif 67.5 <= angle < 112.5:
        return "S"
    elif 112.5 <= angle < 157.5:
        return "SW"
    elif angle >= 157.5 or angle < -157.5:
        return "W"
    elif -157.5 <= angle < -112.5:
        return "NW"
    elif -112.5 <= angle < -67.5:
        return "N"
    elif -67.5 <= angle < -22.5:
        return "NE"

    return None


def estimate_lane(centroid_history: deque, frame_width: int = 960) -> Optional[str]:
    """
    Estimate lane position based on horizontal position in frame.
    Divides frame into 3 equal zones: LEFT, CENTER, RIGHT.

    Args:
        centroid_history: deque of (cx, cy, timestamp) tuples.
        frame_width: Width of the frame in pixels.

    Returns:
        Lane string or None.
    """
    if not centroid_history or len(centroid_history) < 1:
        return None

    # Use mean X position
    x_positions = [pt[0] for pt in centroid_history]
    mean_x = np.mean(x_positions)

    third = frame_width / 3.0
    if mean_x < third:
        return "LEFT"
    elif mean_x < 2 * third:
        return "CENTER"
    else:
        return "RIGHT"


def estimate_dwell_time(track: dict) -> float:
    """
    Calculate how long a vehicle has been visible in the camera's field of view.

    Args:
        track: Tracked object dict with first_seen_time and last_seen_time.

    Returns:
        Dwell time in seconds.
    """
    first = track.get("first_seen_time", 0)
    last = track.get("last_seen_time", 0)
    if first and last:
        return max(0.0, last - first)
    return 0.0


def estimate_pixel_speed(centroid_history: deque) -> float:
    """
    Calculate pixel speed (pixels per second) from centroid history.
    This is NOT real-world speed — it requires camera calibration for km/h conversion.

    Args:
        centroid_history: deque of (cx, cy, timestamp) tuples.

    Returns:
        Speed in pixels per second, or 0.0 if insufficient data.
    """
    if not centroid_history or len(centroid_history) < 2:
        return 0.0

    # Use last 10 entries for smooth speed estimate
    recent = list(centroid_history)[-10:]
    if len(recent) < 2:
        return 0.0

    total_dist = 0.0
    for i in range(1, len(recent)):
        dx = recent[i][0] - recent[i-1][0]
        dy = recent[i][1] - recent[i-1][1]
        total_dist += math.hypot(dx, dy)

    total_time = recent[-1][2] - recent[0][2]
    if total_time <= 0:
        return 0.0

    return total_dist / total_time


def estimate_speed_kmh(centroid_history: deque, pixels_per_meter: Optional[float] = None) -> Optional[float]:
    """
    Estimate real-world speed in km/h if calibration is available.

    Args:
        centroid_history: deque of (cx, cy, timestamp) tuples.
        pixels_per_meter: Camera calibration factor. If None, returns None.

    Returns:
        Speed in km/h, or None if calibration is unavailable.
    """
    if pixels_per_meter is None or pixels_per_meter <= 0:
        return None

    pixel_speed = estimate_pixel_speed(centroid_history)
    if pixel_speed <= 0:
        return None

    # Convert: pixels/sec → meters/sec → km/h
    meters_per_sec = pixel_speed / pixels_per_meter
    kmh = meters_per_sec * 3.6
    return round(kmh, 1)


def compute_trajectory(centroid_history: deque) -> List[Dict]:
    """
    Returns a simplified trajectory as a list of points with timestamps.
    Useful for visualization and database storage.

    Args:
        centroid_history: deque of (cx, cy, timestamp) tuples.

    Returns:
        List of {"x": float, "y": float, "t": float} dicts.
    """
    if not centroid_history:
        return []
    return [{"x": round(pt[0], 1), "y": round(pt[1], 1), "t": pt[2]}
            for pt in centroid_history]


def get_movement_summary(track: dict, frame_width: int = 960,
                         pixels_per_meter: Optional[float] = None) -> Dict:
    """
    Compute a full movement summary for a tracked object.

    Args:
        track: Tracked object dict from ZeroTrailTracker.
        frame_width: Width of the video frame.
        pixels_per_meter: Camera calibration factor (or None).

    Returns:
        Dict with direction, lane, dwell_seconds, pixel_speed, speed_kmh, trajectory.
    """
    history = track.get("centroid_history", deque())

    direction = estimate_direction(history)
    lane = estimate_lane(history, frame_width)
    dwell = estimate_dwell_time(track)
    pixel_speed = estimate_pixel_speed(history)
    speed_kmh = estimate_speed_kmh(history, pixels_per_meter)

    return {
        "direction": direction,
        "lane": lane,
        "dwell_seconds": round(dwell, 1),
        "pixel_speed": round(pixel_speed, 1),
        "speed_kmh": speed_kmh,  # None if no calibration
        "trajectory_points": len(history),
    }
