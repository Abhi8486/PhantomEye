import sys
sys.path.insert(0, ".")
import cv2
import numpy as np
from pathlib import Path
from ultralytics import YOLO

STREAMS_DIR = Path("c:/projects/crime_tracking/PhantomEye-main/PhantomEye-main/data/recorded_streams")
model = YOLO("yolov8s.pt")

cap = cv2.VideoCapture(str(STREAMS_DIR / "cam04.mp4"))
print("Inspecting cam04.mp4...")
for f in [10, 15, 40, 45, 65]:
    cap.set(cv2.CAP_PROP_POS_FRAMES, f)
    ret, frame = cap.read()
    if not ret or frame is None:
        continue
    results = model(frame, imgsz=640, conf=0.35, device="cuda", verbose=False)[0]
    print(f"\n--- Frame {f} ---")
    for box in results.boxes:
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        bw, bh = x2 - x1, y2 - y1
        ar = bh / float(bw) if bw > 0 else 0
        if cls_id == 0 and conf >= 0.48 and bh >= 50 and bw >= 20 and 1.35 <= ar <= 4.2:
            crop = frame[y1:y2, x1:x2]
            ch, cw = crop.shape[:2]
            torso = crop[int(ch * 0.15):int(ch * 0.55), :]
            if torso.size > 0:
                hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
                red_m = ((hsv[:,:,0] < 16) | (hsv[:,:,0] > 164)) & (hsv[:,:,1] > 45) & (hsv[:,:,2] > 45)
                blue_m = (hsv[:,:,0] >= 85) & (hsv[:,:,0] <= 135) & (hsv[:,:,1] > 35) & (hsv[:,:,2] > 35)
                green_m = (hsv[:,:,0] >= 35) & (hsv[:,:,0] < 85) & (hsv[:,:,1] > 35) & (hsv[:,:,2] > 35)
                
                tot = max(1, torso.shape[0] * torso.shape[1])
                rr = np.sum(red_m)/tot
                br = np.sum(blue_m)/tot
                gr = np.sum(green_m)/tot
                print(f"  Person Box=[{x1},{y1},{x2},{y2}], Conf={conf:.2f}: RedRatio={rr:.1%}, BlueRatio={br:.1%}, GreenRatio={gr:.1%}")
