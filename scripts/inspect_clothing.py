import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
from core_ai.detector import RealTimeDetector

detector = RealTimeDetector()
streams_dir = Path('c:/projects/crime_tracking/PhantomEye-main/PhantomEye-main/data/recorded_streams')

def get_color(crop):
    ch, cw = crop.shape[:2]
    torso = crop[int(ch*0.20):int(ch*0.50), int(cw*0.20):int(cw*0.80)]
    if torso.size == 0:
        return 'Unknown', 0.0
    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    tot = max(1, torso.shape[0]*torso.shape[1])
    
    # True Red fabric: H in [0, 10] or [170, 180], but S > 85, V > 60
    is_red = ((hsv[:,:,0] <= 10) | (hsv[:,:,0] >= 170)) & (hsv[:,:,1] > 85) & (hsv[:,:,2] > 60)
    is_blue = (hsv[:,:,0] >= 88) & (hsv[:,:,0] <= 135) & (hsv[:,:,1] > 45) & (hsv[:,:,2] > 40)
    is_green = (hsv[:,:,0] >= 35) & (hsv[:,:,0] <= 85) & (hsv[:,:,1] > 40) & (hsv[:,:,2] > 40)
    is_yellow = (hsv[:,:,0] >= 15) & (hsv[:,:,0] < 35) & (hsv[:,:,1] > 65) & (hsv[:,:,2] > 60)
    is_white = (hsv[:,:,1] < 35) & (hsv[:,:,2] > 120)
    is_black = (hsv[:,:,2] < 50)
    
    r_red = np.sum(is_red) / tot
    r_blue = np.sum(is_blue) / tot
    r_green = np.sum(is_green) / tot
    r_yellow = np.sum(is_yellow) / tot
    r_white = np.sum(is_white) / tot
    r_black = np.sum(is_black) / tot
    
    counts = {'Red': r_red, 'Blue': r_blue, 'Green': r_green, 'Yellow': r_yellow, 'White': r_white, 'Black': r_black}
    best_c, best_r = max(counts.items(), key=lambda x: x[1])
    if best_r >= 0.20:
        return best_c, round(best_r, 2)
    return 'Dark', round(best_r, 2)

for vid in sorted(streams_dir.glob('cam*.mp4')):
    cap = cv2.VideoCapture(str(vid))
    f_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if f_idx % 15 == 0:
            res = detector.detect(frame)
            for d in res['detections']:
                if d['is_person']:
                    bx1, by1, bx2, by2 = d['box']
                    crop = frame[by1:by2, bx1:bx2]
                    col, r = get_color(crop)
                    b = d['box']
                    print(f"{vid.name} f={f_idx} col={col} ({r}) box={b}")
        f_idx += 1
    cap.release()
