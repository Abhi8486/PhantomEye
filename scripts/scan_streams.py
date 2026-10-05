import sys
sys.path.insert(0, ".")
import cv2
from pathlib import Path
from core_ai.detector import RealTimeDetector

streams_dir = Path("c:/projects/crime_tracking/PhantomEye-main/PhantomEye-main/data/recorded_streams")
detector = RealTimeDetector()

for mp4 in sorted(streams_dir.glob("cam*.mp4")):
    cap = cv2.VideoCapture(str(mp4))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    print(f"=== {mp4.name} (Total frames: {total_frames}, FPS: {fps:.1f}) ===")
    
    # Sample 5 frames across the video
    for f_idx in [10, 50, 100, 150, 200]:
        if f_idx < total_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret, frame = cap.read()
            if ret and frame is not None:
                res = detector.detect(frame)
                dets = [(d['class_name'], f"{d['confidence']:.2f}") for d in res['detections']]
                print(f"  Frame {f_idx}: {dets[:6]}")
    cap.release()
