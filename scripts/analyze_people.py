import sys
sys.path.insert(0, ".")
import cv2
import numpy as np
from pathlib import Path
from core_ai.detector import RealTimeDetector

streams_dir = Path("c:/projects/crime_tracking/PhantomEye-main/PhantomEye-main/data/recorded_streams")
detector = RealTimeDetector()

for mp4 in [streams_dir / "cam10.mp4", streams_dir / "cam02.mp4", streams_dir / "cam04.mp4", streams_dir / "cam05.mp4"]:
    if not mp4.exists():
        continue
    cap = cv2.VideoCapture(str(mp4))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"\n=================== {mp4.name} ===================")
    for f_idx in range(10, min(total_frames, 300), 30):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        res = detector.detect(frame)
        for i, d in enumerate(res["detections"]):
            if d["is_person"] or d["class_name"] == "person":
                x1, y1, x2, y2 = d["box"]
                fh, fw = frame.shape[:2]
                crop = frame[max(0, y1):min(fh, y2), max(0, x1):min(fw, x2)]
                if crop.size > 0:
                    # Analyze upper body (top 50% of person box)
                    ch, cw = crop.shape[:2]
                    torso = crop[:int(ch * 0.55), :]
                    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
                    m_hsv = np.mean(hsv, axis=(0, 1))
                    h_val, s_val, v_val = m_hsv[0], m_hsv[1], m_hsv[2]
                    
                    if (h_val < 15 or h_val > 165) and s_val > 45:
                        shirt_color = "Red"
                    elif 15 <= h_val < 38 and s_val > 40:
                        shirt_color = "Yellow/Orange"
                    elif 38 <= h_val < 85 and s_val > 35:
                        shirt_color = "Green"
                    elif 85 <= h_val < 135 and s_val > 35:
                        shirt_color = "Blue"
                    elif v_val < 65:
                        shirt_color = "Black"
                    elif s_val < 45 and v_val > 140:
                        shirt_color = "White"
                    elif s_val < 45:
                        shirt_color = "Grey"
                    else:
                        shirt_color = "Red" if h_val < 20 or h_val > 160 else "Dark"
                    
                    print(f"  Frame {f_idx} Person #{i}: conf={d['confidence']:.2f}, Box=[{x1},{y1},{x2},{y2}], HSV=({h_val:.1f}, {s_val:.1f}, {v_val:.1f}) -> Torso Color: {shirt_color}")
    cap.release()
