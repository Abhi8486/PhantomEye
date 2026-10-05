import cv2
from pathlib import Path

STREAMS_DIR = Path("c:/projects/crime_tracking/PhantomEye-main/PhantomEye-main/data/recorded_streams")

print(f"{'Video':<12} | {'Width':<6} | {'Height':<6} | {'FPS':<6} | {'Frames':<7} | {'Duration (s)':<12}")
print("-" * 65)

for mp4 in sorted(STREAMS_DIR.glob("cam*.mp4")):
    cap = cv2.VideoCapture(str(mp4))
    if not cap.isOpened():
        continue
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    dur = frames / fps if fps > 0 else 0
    print(f"{mp4.name:<12} | {w:<6} | {h:<6} | {fps:<6.1f} | {frames:<7} | {dur:<12.1f}")
    cap.release()
