"""
Tests real YOLOv8 inference across all recorded stream MP4 files and extracts real vehicle/person bounding boxes and colors.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
from core_ai.detector import RealTimeDetector

detector = RealTimeDetector()
streams_dir = Path("c:/projects/crime_tracking/PhantomEye-main/PhantomEye-main/data/recorded_streams")

def extract_dominant_color(crop_bgr):
    if crop_bgr is None or crop_bgr.size == 0:
        return "Unknown"
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    mean_val = np.mean(crop_bgr, axis=(0, 1))
    mean_hsv = np.mean(hsv, axis=(0, 1))
    
    h, s, v = mean_hsv[0], mean_hsv[1], mean_hsv[2]
    
    if v < 45:
        return "Black"
    if s < 35 and v > 150:
        return "White"
    if s < 45:
        return "Silver/Grey"
    if (h < 10 or h > 170) and s > 50:
        return "Red"
    if 15 <= h <= 35:
        return "Yellow"
    if 35 < h <= 85:
        return "Green"
    if 85 < h <= 135:
        return "Blue"
    return "White"

for i in range(1, 9):
    mp4_path = streams_dir / f"cam{i:02d}.mp4"
    if not mp4_path.exists():
        continue
    cap = cv2.VideoCapture(str(mp4_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, 75)
    ret, frame = cap.read()
    cap.release()
    if ret and frame is not None:
        res = detector.detect(frame)
        print(f"\n=== CAM{i:02d} ({frame.shape[1]}x{frame.shape[0]}): {len(res['detections'])} objects detected ===")
        for d in res["detections"][:6]:
            x1, y1, x2, y2 = d["box"]
            crop = frame[y1:y2, x1:x2]
            color = extract_dominant_color(crop)
            print(f"  - {d['class_name']} ({d['confidence']:.2f}): box=({x1}, {y1}, {x2}, {y2}), color={color}")
