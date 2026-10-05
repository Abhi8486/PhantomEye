import sys
sys.path.insert(0, ".")
import cv2
import numpy as np
from pathlib import Path
from ultralytics import YOLO

STREAMS_DIR = Path("c:/projects/crime_tracking/PhantomEye-main/PhantomEye-main/data/recorded_streams")
model = YOLO("yolov8s.pt")

for mp4 in [STREAMS_DIR / "cam02.mp4", STREAMS_DIR / "cam04.mp4", STREAMS_DIR / "cam10.mp4", STREAMS_DIR / "cam01.mp4"]:
    if not mp4.exists():
        continue
    cap = cv2.VideoCapture(str(mp4))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"\n=================== {mp4.name} (Total: {total_frames}) ===================")
    
    for f_idx in [10, 50, 100, 150, 200]:
        if f_idx >= total_frames:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        
        results = model(frame, imgsz=640, conf=0.35, device="cuda" if cv2.cuda.getCudaEnabledDeviceCount() > 0 else "cpu", verbose=False)[0]
        
        real_humans = []
        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            if cls_id == 0 and conf >= 0.50:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                w = x2 - x1
                h = y2 - y1
                ar = h / float(w) if w > 0 else 0
                area = w * h
                # Stricter human anatomical filter:
                # 1. Height >= 55px
                # 2. Width >= 22px
                # 3. Aspect ratio 1.5 <= ar <= 4.0
                # 4. Area >= 1400px^2
                if h >= 55 and w >= 22 and 1.5 <= ar <= 4.0 and area >= 1400:
                    # Torso color
                    crop = frame[y1:y2, x1:x2]
                    torso = crop[int(h * 0.15):int(h * 0.55), :]
                    if torso.size > 0:
                        hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
                        # Dominant color check using pixel histogram thresholding (not just mean!)
                        # Count red pixels (H < 15 or H > 165, S > 50, V > 50)
                        red_mask = ((hsv[:,:,0] < 15) | (hsv[:,:,0] > 165)) & (hsv[:,:,1] > 50) & (hsv[:,:,2] > 50)
                        blue_mask = (hsv[:,:,0] >= 85) & (hsv[:,:,0] <= 135) & (hsv[:,:,1] > 40) & (hsv[:,:,2] > 40)
                        green_mask = (hsv[:,:,0] >= 35) & (hsv[:,:,0] < 85) & (hsv[:,:,1] > 40) & (hsv[:,:,2] > 40)
                        white_mask = (hsv[:,:,1] < 35) & (hsv[:,:,2] > 150)
                        black_mask = (hsv[:,:,2] < 55)
                        
                        total_torso_px = torso.shape[0] * torso.shape[1]
                        red_ratio = np.sum(red_mask) / total_torso_px
                        blue_ratio = np.sum(blue_mask) / total_torso_px
                        green_ratio = np.sum(green_mask) / total_torso_px
                        white_ratio = np.sum(white_mask) / total_torso_px
                        black_ratio = np.sum(black_mask) / total_torso_px
                        
                        if red_ratio > 0.20:
                            dominant = f"RED ({red_ratio:.0%})"
                        elif blue_ratio > 0.20:
                            dominant = f"BLUE ({blue_ratio:.0%})"
                        elif green_ratio > 0.20:
                            dominant = f"GREEN ({green_ratio:.0%})"
                        elif white_ratio > 0.35:
                            dominant = f"WHITE ({white_ratio:.0%})"
                        elif black_ratio > 0.35:
                            dominant = f"BLACK ({black_ratio:.0%})"
                        else:
                            dominant = "GREY/NEUTRAL"
                        
                        real_humans.append(f"Box=[{x1},{y1},{x2},{y2}], AR={ar:.2f}, H={h}, Conf={conf:.2f}, Shirt={dominant}")
        print(f"  Frame {f_idx}: Found {len(real_humans)} verified real humans:")
        for rh in real_humans:
            print(f"    -> {rh}")
    cap.release()
