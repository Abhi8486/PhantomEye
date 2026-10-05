import sys
sys.path.insert(0, ".")
import cv2
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from core_ai.detector import RealTimeDetector
from core_ai.tracker import ZeroTrailTracker
from core_ai.reid_extractor import reid_extractor

STREAMS_DIR = Path("c:/projects/crime_tracking/PhantomEye-main/PhantomEye-main/data/recorded_streams")
detector = RealTimeDetector()

def test_pipeline(mp4_name, camera_id="CAM-004"):
    mp4_path = STREAMS_DIR / mp4_name
    cap = cv2.VideoCapture(str(mp4_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    print(f"\n==================== Tracking {mp4_name} ({total_frames} frames @ {fps} fps) ====================")
    
    tracker = ZeroTrailTracker(max_missed=3)
    base_time = datetime(2026, 9, 3, 13, 40, 0)
    
    track_records = {}
    
    frame_idx = 0
    step = 2
    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break
            
        if frame_idx % step == 0:
            v_sec = frame_idx / fps
            frame_ts = base_time + timedelta(seconds=v_sec)
            ts_str = frame_ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
            # Detect
            res = detector.detect(frame)
            tracked = tracker.update(res["detections"])
            
            for tid, t in tracked.items():
                if tid not in track_records:
                    track_records[tid] = {
                        "track_id": tid,
                        "class_name": t["class_name"],
                        "is_person": t["is_person"],
                        "is_vehicle": t["is_vehicle"],
                        "frames": [],
                        "best_conf": 0.0,
                        "best_crop": None,
                        "best_bbox": None,
                        "best_ts": None,
                        "first_ts": ts_str,
                        "last_ts": ts_str
                    }
                rec = track_records[tid]
                rec["frames"].append(frame_idx)
                rec["last_ts"] = ts_str
                
                # Check if best crop
                conf = t["confidence"]
                bx1, by1, bx2, by2 = t["box"]
                bw, bh = bx2 - bx1, by2 - by1
                if conf > rec["best_conf"] and bw >= 20 and bh >= 20:
                    rec["best_conf"] = conf
                    rec["best_bbox"] = t["box"]
                    rec["best_ts"] = ts_str
                    crop = frame[max(0, by1):min(frame.shape[0], by2), max(0, bx1):min(frame.shape[1], bx2)]
                    if crop.size > 0:
                        rec["best_crop"] = crop.copy()
        
        frame_idx += 1
    
    cap.release()
    print(f"[+] Total Tracks Created: {len(track_records)}")
    
    for tid, rec in list(track_records.items())[:10]:
        dur_frames = len(rec["frames"])
        if rec["is_person"] and rec["best_crop"] is not None:
            crop = rec["best_crop"]
            ch, cw = crop.shape[:2]
            
            # Upper Torso (15% - 50%)
            torso = crop[int(ch * 0.15):int(ch * 0.50), :]
            # Lower Legs / Pants (60% - 95%)
            legs = crop[int(ch * 0.60):int(ch * 0.95), :]
            
            def get_dom_color(patch):
                if patch.size == 0: return "Unknown"
                hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
                tot = max(1, patch.shape[0] * patch.shape[1])
                r_m = ((hsv[:,:,0] < 16) | (hsv[:,:,0] > 164)) & (hsv[:,:,1] > 40) & (hsv[:,:,2] > 40)
                b_m = (hsv[:,:,0] >= 85) & (hsv[:,:,0] <= 135) & (hsv[:,:,1] > 30) & (hsv[:,:,2] > 30)
                g_m = (hsv[:,:,0] >= 30) & (hsv[:,:,0] <= 85) & (hsv[:,:,1] > 25) & (hsv[:,:,2] > 30)
                w_m = (hsv[:,:,1] < 35) & (hsv[:,:,2] > 135)
                k_m = (hsv[:,:,2] < 55)
                
                ratios = {"Red": np.sum(r_m)/tot, "Blue": np.sum(b_m)/tot, "Green": np.sum(g_m)/tot, "White": np.sum(w_m)/tot, "Black": np.sum(k_m)/tot}
                best_c, best_val = max(ratios.items(), key=lambda x: x[1])
                return best_c if best_val >= 0.18 else "Grey/Dark"

            upper_c = get_dom_color(torso)
            lower_c = get_dom_color(legs)
            
            # Deep Re-ID vector
            emb = reid_extractor.extract_embedding(crop)
            
            print(f"  Track #{tid} (Person): {dur_frames} detections ({rec['first_ts']} -> {rec['last_ts']})")
            print(f"    -> Upper: {upper_c} | Lower: {lower_c} | Conf: {rec['best_conf']:.2f} | BBox: {rec['best_bbox']} | EmbNorm: {np.linalg.norm(emb):.2f}")

test_pipeline("cam04.mp4")
test_pipeline("cam10.mp4")
