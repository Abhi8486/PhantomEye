import sys
sys.path.insert(0, ".")
import cv2
import numpy as np
from pathlib import Path
from core_ai.detector import RealTimeDetector

STREAMS_DIR = Path("c:/projects/crime_tracking/PhantomEye-main/PhantomEye-main/data/recorded_streams")
detector = RealTimeDetector()

print("[*] Testing video timeline indexing across streams...")

CAMERAS_META = [
    ("CAM-001", "01 Chiman bhai Bridge", "Ahmedabad", 23.0785, 72.5840, "cam01.mp4"),
    ("CAM-002", "02 Janpath", "Ahmedabad", 23.0560, 72.5710, "cam02.mp4"),
    ("CAM-003", "03 Gandhinagar Sector 21", "Gandhinagar", 23.2156, 72.6369, "cam03.mp4"),
    ("CAM-004", "04 Visat teen Rasta P1", "Ahmedabad", 23.0970, 72.5850, "cam04.mp4"),
    ("CAM-005", "05 Visat teen Rasta", "Ahmedabad", 23.0975, 72.5855, "cam05.mp4"),
    ("CAM-006", "06 SG Highway Infocity", "Gandhinagar", 23.1890, 72.6280, "cam06.mp4"),
    ("CAM-008", "08 Motera Stadium Cross Road", "Ahmedabad", 23.0920, 72.5980, "cam08.mp4"),
    ("CAM-009", "09 Sarkhej Highway", "Ahmedabad", 22.9860, 72.5020, "cam09.mp4"),
    ("CAM-010", "10 Ring Road Intersection", "Ahmedabad", 23.0300, 72.5800, "cam10.mp4"),
    ("CAM-012", "12 Tri Mandir Adalaj Tollnaka", "Gandhinagar", 23.1760, 72.5790, "cam02.mp4"),
    ("CAM-016", "16 Visat P2", "Ahmedabad", 23.0990, 72.5865, "cam05.mp4"),
    ("CAM-022", "28 BK Mervada tran Rasta", "Banaskantha", 24.1640, 72.4200, "cam04.mp4"),
    ("CAM-024", "33 dehgam", "Gandhinagar", 23.1680, 72.8120, "cam01.mp4"),
    ("CAM-025", "25 Surat Ring Road Junction", "Surat", 21.1702, 72.8311, "cam10.mp4"),
    ("CAM-028", "28 Rajkot Racecourse Circle", "Rajkot", 22.3039, 70.8022, "cam04.mp4"),
    ("CAM-030", "30 Vadodara Alkapuri", "Vadodara", 22.3072, 73.1812, "cam02.mp4"),
]

all_indexed = []

for cid, cname, city, lat, lng, vid_file in CAMERAS_META:
    mp4_path = STREAMS_DIR / vid_file
    if not mp4_path.exists():
        continue
    cap = cv2.VideoCapture(str(mp4_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    # Sample 4 frame timestamps per video
    sample_offsets = [15, 60, 120, 180] if total_frames > 200 else [10, 35, 55]
    for f_off in sample_offsets:
        if f_off >= total_frames:
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, f_off)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        
        res = detector.detect(frame)
        fh, fw = frame.shape[:2]
        
        for d in res["detections"]:
            x1, y1, x2, y2 = d["box"]
            crop = frame[max(0, y1):min(fh, y2), max(0, x1):min(fw, x2)]
            if crop.size == 0 or (x2 - x1) < 20 or (y2 - y1) < 20:
                continue
            
            is_person = d["is_person"] or d["class_name"] == "person"
            if is_person:
                # Analyze torso for person clothing color
                ch = crop.shape[0]
                torso = crop[:int(ch * 0.55), :]
                hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
                m_hsv = np.mean(hsv, axis=(0, 1))
                h_val, s_val, v_val = m_hsv[0], m_hsv[1], m_hsv[2]
                
                if (h_val < 15 or h_val > 165) and s_val > 38:
                    col = "Red"
                elif 15 <= h_val < 38 and s_val > 35:
                    col = "Yellow"
                elif 38 <= h_val < 85 and s_val > 30:
                    col = "Green"
                elif 85 <= h_val < 135 and s_val > 30:
                    col = "Blue"
                elif v_val < 65:
                    col = "Black"
                elif s_val < 40 and v_val > 140:
                    col = "White"
                elif s_val < 45:
                    col = "Grey"
                else:
                    col = "Red" if h_val < 22 or h_val > 158 else "Dark"
                
                obj_type = "PERSON"
            else:
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                m_hsv = np.mean(hsv, axis=(0, 1))
                h_val, s_val, v_val = m_hsv[0], m_hsv[1], m_hsv[2]
                
                if v_val < 55:
                    col = "Black"
                elif s_val < 40 and v_val > 135:
                    col = "White"
                elif s_val < 45:
                    col = "Silver"
                elif (h_val < 12 or h_val > 168) and s_val > 45:
                    col = "Red"
                elif 15 <= h_val <= 35:
                    col = "Yellow"
                elif 35 < h_val <= 85:
                    col = "Green"
                elif 85 < h_val <= 135:
                    col = "Blue"
                else:
                    col = "White"
                
                obj_type = "BUS" if "bus" in d["class_name"] else "TRUCK" if "truck" in d["class_name"] else "SUV/Car"

            all_indexed.append({
                "camera_id": cid,
                "camera_name": cname,
                "city": city,
                "frame_offset": f_off,
                "object_type": obj_type,
                "color": col,
                "confidence": d["confidence"],
                "box": (x1, y1, x2, y2)
            })
    cap.release()

print(f"[OK] Total indexed objects across video timelines: {len(all_indexed)}")
people_counts = {}
for item in all_indexed:
    if item["object_type"] == "PERSON":
        c = item["color"]
        people_counts[c] = people_counts.get(c, 0) + 1

print(f"People indexed by clothing color: {people_counts}")
