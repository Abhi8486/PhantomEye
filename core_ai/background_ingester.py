"""
Background Ingestion Daemon
Continuously monitors all active cameras using a lightweight ThreadPool,
fetches frames using the Indexer's cache to prevent memory exhaustion,
tracks vehicles to prevent duplicates, and logs ALL vehicles to the database.
"""

import time
import uuid
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np
import json

def get_vehicle_color(crop_bgr):
    if crop_bgr is None or crop_bgr.size == 0:
        return "Unknown"
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    h, w = hsv.shape[:2]
    # Use central region to avoid background
    chsv = hsv[int(h*0.3):int(h*0.7), int(w*0.3):int(w*0.7)]
    if chsv.size == 0: return "Unknown"
    
    avg = np.mean(chsv, axis=(0,1))
    hue, sat, val = avg
    
    if val < 45: return "Black"
    if val > 200 and sat < 40: return "White"
    if sat < 50: return "Silver/Grey"
    if hue < 10 or hue > 160: return "Red"
    if hue >= 10 and hue < 25: return "Orange"
    if hue >= 25 and hue < 35: return "Yellow"
    if hue >= 35 and hue < 85: return "Green"
    if hue >= 85 and hue < 130: return "Blue"
    return "Unknown"

from core_ai.detector import RealTimeDetector
from core_ai.tracker import ZeroTrailTracker
from core_ai.anpr import ANPREngine
from core_ai.ocr_fusion import OCRFusionEngine
from backend.database.schema import get_db_connection
from backend.routers.alerts import alert_manager
from core_ai.indexer import fetch_dynamic_live_frame

class CameraState:
    """Holds the tracker and OCR fusion engine for a specific camera."""
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.tracker = ZeroTrailTracker(max_missed=15)
        self.ocr_fusion = OCRFusionEngine()
        self.frame_count = 0
        self.vehicle_state = {}

class BackgroundIngesterDaemon:
    def __init__(self):
        self.running = False
        self.thread = None
        self.camera_states = {}
        # Share a single detector and ANPR engine across workers to save VRAM/Memory
        self.detector = RealTimeDetector(conf_thresh=0.25)
        self.anpr_engine = ANPREngine(use_gpu=True)
        # Limit concurrent processing to 4 threads to prevent CPU/Mem lockup
        self.pool = ThreadPoolExecutor(max_workers=4)
        
    def start(self):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        print("[BackgroundIngester] Daemon started with optimized thread pool.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=3.0)
        self.pool.shutdown(wait=False)
        print("[BackgroundIngester] Daemon stopped.")

    def _monitor_loop(self):
        while self.running:
            try:
                # 1. Fetch active cameras
                conn = get_db_connection()
                rows = conn.execute("SELECT camera_id FROM cameras WHERE status = 'ACTIVE';").fetchall()
                conn.close()
                
                active_cids = [row["camera_id"] for row in rows]
                
                # Setup states for new cameras
                for cid in active_cids:
                    if cid not in self.camera_states:
                        self.camera_states[cid] = CameraState(cid)
                        
                # 2. Submit a batch of processing jobs (one for each camera)
                # We use the thread pool so only 4 process concurrently.
                futures = []
                for cid in active_cids:
                    if not self.running: break
                    fut = self.pool.submit(self._process_camera_tick, cid)
                    futures.append(fut)
                
                # Wait for all cameras to be processed in this tick
                for fut in futures:
                    try:
                        fut.result(timeout=5.0)
                    except Exception:
                        pass
                
                self._cleanup_old_events()
                
                # Sleep a bit before the next global tick to keep FPS low (~1-2 FPS per cam)
                time.sleep(1.0)
                
            except Exception as e:
                print(f"[BackgroundIngester] Global monitor loop error: {e}")
                time.sleep(5.0)

    def _process_camera_tick(self, cid: str):
        """Processes a single frame for a specific camera."""
        if not self.running: return
        
        state = self.camera_states.get(cid)
        if not state: return
        
        try:
            # Uses indexer's caching and safe offline detection to avoid blocking
            frame = fetch_dynamic_live_frame(cid)
            if frame is None or frame.size == 0:
                return
                
            # If the frame is the offline placeholder, skip AI processing
            if np.mean(frame) < 20 and "LIVE FEED RE-CONNECTING" in str(frame.tobytes()):
                return
                
            state.frame_count += 1
            frame_disp = cv2.resize(frame, (960, 540))
            
            # Detect & Track
            det_res = self.detector.detect(frame_disp)
            tracked = state.tracker.update(det_res["detections"])
            active_tids = set(tracked.keys())
            
            for tid, obj in tracked.items():
                if not obj["is_vehicle"]:
                    continue
                    
                if tid not in state.vehicle_state:
                    state.vehicle_state[tid] = {
                        "logged_event": False,
                        "ocr_attempted": False,
                        "plate_logged": False,
                        "best_score": 0.0,
                        "best_crop": None,
                        "last_seen": state.frame_count,
                        "hit_streak": 1,
                        "obj": obj
                    }
                else:
                    state.vehicle_state[tid]["hit_streak"] += 1
                
                vstate = state.vehicle_state[tid]
                vstate["last_seen"] = state.frame_count
                vstate["obj"] = obj
                
                # Log event
                if not vstate["logged_event"] and vstate["hit_streak"] >= 1:
                    # Extract initial crop for color analysis
                    color_name = "Unknown"
                    x1, y1, x2, y2 = obj["box"]
                    if (y2 - y1) > 20 and (x2 - x1) > 20:
                        scale_x = frame.shape[1] / 960.0
                        scale_y = frame.shape[0] / 540.0
                        ox1, oy1 = max(0, int(x1 * scale_x)), max(0, int(y1 * scale_y))
                        ox2, oy2 = min(frame.shape[1], int(x2 * scale_x)), min(frame.shape[0], int(y2 * scale_y))
                        initial_crop = frame[oy1:oy2, ox1:ox2]
                        color_name = get_vehicle_color(initial_crop)
                        
                    self._log_vehicle_event(cid, tid, obj, color_name)
                    vstate["logged_event"] = True
                    
                # OCR Check
                conf = obj.get("confidence", 0.0)
                if conf > vstate["best_score"]:
                    x1, y1, x2, y2 = obj["box"]
                    if (y2 - y1) > 40 and (x2 - x1) > 40:
                        scale_x = frame.shape[1] / 960.0
                        scale_y = frame.shape[0] / 540.0
                        ox1, oy1 = max(0, int(x1 * scale_x)), max(0, int(y1 * scale_y))
                        ox2, oy2 = min(frame.shape[1], int(x2 * scale_x)), min(frame.shape[0], int(y2 * scale_y))
                        crop = frame[oy1:oy2, ox1:ox2]
                        if crop.size > 0:
                            vstate["best_crop"] = crop
                            vstate["best_score"] = conf
                            
                if vstate["best_crop"] is not None and not vstate["plate_logged"]:
                    plate_data = self.anpr_engine.read_plate(vstate["best_crop"], allow_gemini_fallback=False)
                    if plate_data and plate_data.get("plate"):
                        confirmed = state.ocr_fusion.add_reading(
                            track_id=tid,
                            text=plate_data["plate"],
                            ocr_confidence=plate_data.get("ocr_confidence", 0.5),
                            quality_score=plate_data.get("quality_score", 0.5),
                            frame_num=state.frame_count,
                            detection_method=plate_data.get("detection_method", "yolo")
                        )
                        if confirmed:
                            self._log_plate(cid, tid, obj, confirmed, vstate["best_crop"])
                            vstate["plate_logged"] = True
            
            # Cleanup
            lost_tids = [t for t, s in state.vehicle_state.items() if state.frame_count - s["last_seen"] > 10]
            for t in lost_tids:
                vstate = state.vehicle_state[t]
                if vstate.get("logged_event") and not vstate.get("plate_logged"):
                    self._mark_detection_failed(cid, t)
                del state.vehicle_state[t]
            state.ocr_fusion.cleanup_stale(active_tids)
            
        except Exception as e:
            # Print minimally so we don't spam terminal
            pass

    def _log_vehicle_event(self, cid, tid, obj, color_name="Unknown"):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            event_id = f"EV-VEH-{uuid.uuid4().hex[:12]}"
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            vehicle_type = obj.get("label", "vehicle").upper()
            
            meta = {
                "color": color_name,
                "confidence": round(float(obj.get("confidence", 0)), 2)
            }
            
            cursor.execute("""
            INSERT INTO vehicle_events (
                event_id, camera_id, vehicle_track_id, event_type, 
                timestamp, direction, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (event_id, cid, tid, vehicle_type, now_str, "Inbound", json.dumps(meta)))
            conn.commit()
            conn.close()
            
            # Broadcast the detection to the UI
            payload = {
                "type": "NEW_VEHICLE_DETECTION",
                "camera_id": cid,
                "vehicle_type": vehicle_type,
                "color": color_name,
                "timestamp": now_str
            }
            try:
                alert_manager.broadcast_sync(payload)
            except Exception:
                pass
        except Exception:
            pass

    def _mark_detection_failed(self, cid, tid):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE vehicle_events SET plate_number = 'DETECTION_FAILED' 
            WHERE camera_id = ? AND vehicle_track_id = ? AND plate_number IS NULL;
            """, (cid, tid))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _log_plate(self, cid, tid, obj, confirmed, crop):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            anpr_id = f"ANPR-BG-{uuid.uuid4().hex[:12]}"
            
            cursor.execute("SELECT city, name FROM cameras WHERE camera_id = ?;", (cid,))
            cam_row = cursor.fetchone()
            city = cam_row["city"] if cam_row else "Gujarat"
            
            from core_ai.anpr import VAHAN_DATABASE, ANPREngine
            vahan = VAHAN_DATABASE.get(confirmed.plate_text, ANPREngine._default_vahan(confirmed.plate_text))
            
            cursor.execute("""
            INSERT INTO vehicle_anpr (
                anpr_id, camera_id, timestamp, plate_number, confidence,
                vehicle_type, vehicle_color, direction, speed_kmh,
                vahan_owner, vahan_model, vahan_status, is_flagged, bbox_json,
                plate_detection_confidence, ocr_confidence, quality_score,
                format_validation, detection_method, multi_frame_agreement, review_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                anpr_id, cid, now_str, confirmed.plate_text, confirmed.final_confidence,
                obj.get("label", "VEHICLE"), vahan.get("color") or "Standard", "Inbound", 0.0,
                vahan.get("owner"), vahan.get("make_model"), vahan.get("status") or "UNLISTED", 
                vahan.get("is_flagged", 0), json.dumps(obj.get("box", [])),
                0.9, confirmed.best_ocr_confidence, confirmed.best_quality_score,
                confirmed.format_validation, confirmed.detection_method, confirmed.agreement_ratio,
                "AUTO_CONFIRMED" if confirmed.final_confidence >= 0.6 else "NEEDS_REVIEW"
            ))
            
            cursor.execute("""
            UPDATE vehicle_events SET plate_number = ? WHERE camera_id = ? AND vehicle_track_id = ?;
            """, (confirmed.plate_text, cid, tid))
            
            conn.commit()
            conn.close()
            
            payload = {
                "type": "NEW_ANPR_DETECTION",
                "plate_number": confirmed.plate_text,
                "vehicle_model": vahan.get("make_model") or obj.get("label", "Vehicle"),
                "vehicle_color": vahan.get("color") or "Standard",
                "camera_id": cid,
                "city": city,
                "is_flagged": bool(vahan.get("is_flagged", False)),
                "timestamp": now_str,
                "final_confidence": confirmed.final_confidence,
                "review_status": "AUTO_CONFIRMED" if confirmed.final_confidence >= 0.6 else "NEEDS_REVIEW",
            }
            try:
                alert_manager.broadcast_sync(payload)
            except Exception:
                pass
        except Exception:
            pass

    def _cleanup_old_events(self):
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
            DELETE FROM vehicle_events 
            WHERE timestamp < ? AND (plate_number IS NULL OR plate_number = 'DETECTION_FAILED');
            """, (seven_days_ago,))
            conn.commit()
            conn.close()
        except Exception:
            pass

ingester_daemon = BackgroundIngesterDaemon()
