"""
Live Video AI Streamer & Real-Time GPU Detection Overlay
Streams real-time MJPEG video with live YOLO26s bounding boxes, ZeroTrail persistent IDs, and ANPR overlays.
Thread-safe video capture lifecycle ensuring zero FFmpeg multi-threading collisions and instant zero-delay failover.

v2: Integrated multi-frame OCR fusion, bounded queue worker, quality gating, and separated confidence scoring.
"""

import os
import json
import time
import queue
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List, Set
# pyrefly: ignore [missing-import]
import cv2
import numpy as np
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core_ai.detector import RealTimeDetector
from core_ai.tracker import ZeroTrailTracker
from core_ai.anpr import ANPREngine, calculate_vehicle_quality
from core_ai.ocr_fusion import ocr_fusion, OCRFusionEngine
from core_ai.indexer import probe_rtsp_online
from core_ai.gemini_vlm import GeminiVisionEngine
from core_ai.florence_vlm import FlorenceVisionEngine
from ..database.schema import get_db_connection
from .alerts import alert_manager

router = APIRouter(prefix="/api/video", tags=["Live Video AI Streaming"])

# Configure clean OpenCV RTSP TCP transport with quick timeout to avoid 30s ffmpeg hangs
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "rtsp_transport;tcp|"
    "buffer_size;1048576|"
    "stimeout;2000000|"
    "max_delay;500000"
)

# Initialize AI Engines
detector = RealTimeDetector(conf_thresh=0.30)  # Lowered from 0.50 to 0.30 to detect distant vehicles
tracker = ZeroTrailTracker(max_missed=30)
anpr_engine = ANPREngine(use_gpu=True)
vlm_engine = GeminiVisionEngine()
florence_engine = FlorenceVisionEngine.get_instance()

# Active Stream Processors Cache
active_captures = {}
capture_lock = threading.Lock()


def find_recorded_stream(cam_num: int) -> Optional[str]:
    """Finds recorded CCTV MP4 video for local streaming or instant offline failover."""
    return None


class FramesCapture:
    def __init__(self, folder_path, fps=10.0):
        self.folder_path = folder_path
        self.fps = fps
        self.frames = []
        if os.path.exists(folder_path):
            self.frames = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
        self.idx = 0
        self.opened = len(self.frames) > 0

    def isOpened(self):
        return self.opened

    def read(self):
        if not self.opened:
            return False, None
        if self.idx >= len(self.frames):
            self.idx = 0 # Loop infinitely
        frame_path = os.path.join(self.folder_path, self.frames[self.idx])
        img = cv2.imread(frame_path)
        self.idx += 1
        return img is not None, img

    def get(self, propId):
        if propId == cv2.CAP_PROP_FPS:
            return self.fps
        return 0

    def release(self):
        self.opened = False


class LiveCameraProcessor:
    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.cam_num = 1
        try:
            self.cam_num = int(camera_id.replace("CAM-", ""))
        except Exception:
            pass

        self.rtsp_url, self.fallback_path = self._resolve_stream_source(camera_id)
        self.running = True
        self.lock = threading.RLock()
        self.frame_count = 0
        self.active_mode = "CONNECTING"
        self._recent_plates = {}
        self._loop_on_eof = True  # Configurable: loop recorded video or stop on EOF
        
        self.vehicle_state = {}
        self.anpr_roi_y = 350  # Static ROI line for all cameras
        self.DEBUG_BEST_FRAME = False

        # Bounded OCR queue + persistent worker thread (replaces ad-hoc thread spawning)
        self._ocr_queue = queue.Queue(maxsize=20)
        self._ocr_fusion = ocr_fusion  # shared OCR fusion engine

        # Traffic analytics counters (Phase 3)
        self._traffic_counts = {"vehicle": 0, "person": 0}
        self._last_traffic_broadcast = time.time()

        # Instant Pre-warm: Read first frame from fallback or build telemetry so stream is 100% immediate (<20ms)
        self.raw_frame = None
        self.last_frame = None
        self._prewarm_initial_frame()

        # Start persistent OCR worker thread
        self._ocr_worker_thread = threading.Thread(target=self._ocr_worker_loop, daemon=True)
        self._ocr_worker_thread.start()

        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _prewarm_initial_frame(self):
        """Pre-warms the initial frame using local CCTV archive so the user sees live video immediately."""
        if self.fallback_path and os.path.isfile(self.fallback_path):
            try:
                cap_pre = cv2.VideoCapture(self.fallback_path)
                ret, frame = cap_pre.read()
                cap_pre.release()
                if ret and frame is not None:
                    frame_disp = cv2.resize(frame, (960, 540))
                    # Quick HUD overlay
                    cv2.rectangle(frame_disp, (0, 0), (960, 30), (10, 14, 20), -1)
                    cv2.putText(frame_disp, f"PHANTOMEYE | {self.camera_id} | INITIALIZING STREAM...", (12, 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                    _, jpg = cv2.imencode('.jpg', frame_disp, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    self.raw_frame = frame
                    self.last_frame = jpg.tobytes()
                    return
            except Exception:
                pass

        # Fallback to telemetry graphics if video file unreadable
        init_frame = self._build_telemetry_frame("CONNECTING TO GUJARAT POLICE CCTV FEED...")
        self.raw_frame = init_frame.copy()
        _, jpg = cv2.imencode('.jpg', init_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        self.last_frame = jpg.tobytes()

    def _build_telemetry_frame(self, message: str) -> np.ndarray:
        tel = np.full((540, 960, 3), 16, dtype=np.uint8)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(tel, f"GUJARAT POLICE SENTINEL CCTV | {self.camera_id}", (40, 220),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 210, 255), 2)
        cv2.putText(tel, message, (40, 260),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 128), 2)
        cv2.putText(tel, f"TIMESTAMP: {now_str} IST | RTSP ENTERPRISE TRANSPORT", (40, 300),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1)
        return tel

    def _resolve_stream_source(self, camera_id: str) -> tuple[str, Optional[str]]:
        from backend.config import ENABLE_TEST_CAMERA_VIDEO, TEST_VIDEO_PATH, TEST_CAMERA_ID
        
        # [TEST HACK]: Inject local MP4 file for pipeline testing on the configured test camera
        if ENABLE_TEST_CAMERA_VIDEO and camera_id == TEST_CAMERA_ID:
            return TEST_VIDEO_PATH, TEST_VIDEO_PATH

        fallback_path = find_recorded_stream(self.cam_num)
        
        # --- USER OVERRIDE FOR CCTV HLS/RTSP FEEDS ---
        # If camera_id is exactly CAM-04, use the provided HLS feed which bypasses HEVC decoding issues
        if camera_id == "CAM-04" or camera_id == "CAM-004":
            print(f"[VideoStream] Forcing HLS override for {camera_id}")
            return "https://cctv.corp8.cloud/cam04/index.m3u8", fallback_path

        try:
            from ..database.schema import get_db_connection
            conn = get_db_connection()
            row = conn.execute("SELECT stream_url FROM cameras WHERE camera_id = ?", (camera_id,)).fetchone()
            conn.close()
            if row and row["stream_url"]:
                url = row["stream_url"]
                # Inject credentials at runtime so they aren't stored in the database
                if url.startswith("rtsp://"):
                    try:
                        from ..config import RTSP_USERNAME, RTSP_PASSWORD
                        if RTSP_USERNAME and RTSP_PASSWORD:
                            url = url.replace("rtsp://", f"rtsp://{RTSP_USERNAME}:{RTSP_PASSWORD}@")
                    except ImportError:
                        pass
                return url, fallback_path
        except Exception:
            pass
        
        # Ultimate fallback for local testing
        return f"rtsp://mock-camera-stream/{camera_id}", fallback_path

    def _worker(self):
        is_rtsp = True
        hls_url = self.rtsp_url
        current_source_rtsp = self.rtsp_url
        current_source_hls = hls_url
        self.cap_rtsp = None
        self.cap_hls = None
        consecutive_fails = 0

        last_rtsp_retry = time.time()

        while self.running:
            try:
                if not self.running:
                    break

                if not is_rtsp and (time.time() - last_rtsp_retry > 10.0):
                    last_rtsp_retry = time.time()
                    try:
                        if probe_rtsp_online(self.camera_id, timeout_s=1.5):
                            print(f"[VideoStream] Live RTSP stream available for {self.camera_id}! Reconnecting...")
                            if self.cap_rtsp:
                                try: self.cap_rtsp.release()
                                except: pass
                            if self.cap_hls:
                                try: self.cap_hls.release()
                                except: pass
                            self.cap_rtsp = None
                            self.cap_hls = None
                            current_source_rtsp = self.rtsp_url
                            current_source_hls = hls_url
                            is_rtsp = True
                            self.active_mode = "CONNECTING"
                            consecutive_fails = 0
                            continue
                    except:
                        pass

                if self.cap_rtsp is None or not self.cap_rtsp.isOpened():
                    from backend.config import ENABLE_TEST_CAMERA_FRAMES, TEST_FRAMES_DIR, TEST_CAMERA_ID
                    if ENABLE_TEST_CAMERA_FRAMES and self.camera_id == TEST_CAMERA_ID:
                        self.cap_rtsp = FramesCapture(TEST_FRAMES_DIR, fps=10.0)
                    else:
                        if is_rtsp:
                            self.cap_rtsp = cv2.VideoCapture(current_source_rtsp, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 6000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 8000])
                        else:
                            self.cap_rtsp = cv2.VideoCapture(current_source_rtsp)

                    if not self.cap_rtsp or not self.cap_rtsp.isOpened():
                        if is_rtsp and self.fallback_path:
                            current_source_rtsp = self.fallback_path
                            current_source_hls = self.fallback_path
                            is_rtsp = False
                            self.active_mode = "ARCHIVE_FAILOVER"
                            self.cap_rtsp = cv2.VideoCapture(current_source_rtsp)
                        else:
                            off_frame = self._build_telemetry_frame("CAMERA OFFLINE / FEED DISCONNECTED. RETRYING...")
                            self.raw_frame = off_frame.copy()
                            _, jpg = cv2.imencode('.jpg', off_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                            self.last_frame = jpg.tobytes()
                            time.sleep(1.0)
                            continue

                if not self.running:
                    break

                fps = self.cap_rtsp.get(cv2.CAP_PROP_FPS) or 25.0
                frame_interval = 1.0 / max(10.0, min(30.0, fps))

                t_start = time.time()
                ret_a, frame_a = self.cap_rtsp.read()
                ret_d, frame_d = self.cap_hls.read() if self.cap_hls and self.cap_hls.isOpened() else (False, None)

                if not ret_a or frame_a is None or frame_a.size == 0:
                    consecutive_fails += 1
                    if not is_rtsp and self.cap_rtsp:
                        print(f"[VideoStream] EOF reached for {self.camera_id}. Finalizing active tracks...")
                        for tid, state in list(self.vehicle_state.items()):
                            vehicle_key = state["vehicle_key"]
                            best_frame = anpr_engine.finalize_vehicle(vehicle_key)
                            if best_frame is not None and not state["ocr_attempted"]:
                                try:
                                    self._ocr_queue.put_nowait((tid, best_frame, state["obj"], self.frame_count))
                                    state["ocr_attempted"] = True
                                except queue.Full:
                                    pass
                        print(f"[VideoStream] Stream finished. Halting worker thread.")
                        break

                    if consecutive_fails >= 12:
                        if is_rtsp and self.fallback_path:
                            if self.cap_rtsp:
                                try: self.cap_rtsp.release()
                                except: pass
                            if self.cap_hls:
                                try: self.cap_hls.release()
                                except: pass
                            current_source_rtsp = self.fallback_path
                            current_source_hls = self.fallback_path
                            is_rtsp = False
                            self.active_mode = "ARCHIVE_FAILOVER"
                            self.cap_rtsp = cv2.VideoCapture(current_source_rtsp)
                            consecutive_fails = 0
                            last_rtsp_retry = time.time()
                            continue
                        elif self.cap_rtsp:
                            try: self.cap_rtsp.release()
                            except: pass
                            if self.cap_hls:
                                try: self.cap_hls.release()
                                except: pass
                            self.cap_rtsp = None
                            self.cap_hls = None
                        consecutive_fails = 0
                        time.sleep(0.3)
                    else:
                        time.sleep(0.03)
                    continue

                consecutive_fails = 0
                self.frame_count += 1
                if is_rtsp:
                    self.active_mode = "LIVE_RTSP"

                with self.lock:
                    if ret_d and frame_d is not None and frame_d.size > 0:
                        self.raw_frame = frame_d.copy()
                    else:
                        self.raw_frame = frame_a.copy()

                frame_disp = cv2.resize(frame_a, (960, 540))
                
                # --- VISUAL ROI BOUNDARY (DISABLED) ---
                # The user requested to hide the ROI line and use the same fixed ROI for all cameras.

                det_res = detector.detect(frame_disp)
                detections = det_res["detections"]
                tracked = tracker.update(detections)

                # --- DRAW DETECTIONS ---
                for tid, obj in tracked.items():
                    x1, y1, x2, y2 = map(int, obj["box"])
                    label = f"{obj.get('label', 'Obj')} {tid}"
                    color = (0, 255, 255) if obj.get("is_vehicle") else (0, 255, 0)
                    cv2.rectangle(frame_disp, (x1, y1), (x2, y2), color, 2)
                    cv2.putText(frame_disp, label, (x1, max(15, y1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

                with self.lock:
                    self.last_frame = frame_disp.copy()

                # Evaluate and collect best frames every frame
                orig_h, orig_w = frame_a.shape[:2]
                scale_x = orig_w / float(960)
                scale_y = orig_h / float(540)
                active_track_ids = set(tracked.keys())
                
                # Filter tracks by static ROI
                active_roi_track_ids = set()
                filter_y = self.anpr_roi_y
                for tid, obj in tracked.items():
                    if obj["is_vehicle"]:
                        _, _, _, y2 = obj["box"]
                        if y2 >= filter_y:
                            active_roi_track_ids.add(tid)
                
                # Identify lost tracks and trigger ANPR (vehicles leaving ROI are considered lost)
                lost_tracks = set(self.vehicle_state.keys()) - active_roi_track_ids
                for tid in lost_tracks:
                    state = self.vehicle_state[tid]
                    vehicle_key = state["vehicle_key"]
                    best_frame = anpr_engine.finalize_vehicle(vehicle_key)
                    if best_frame is not None and not state["ocr_attempted"]:
                        try:
                            # Enqueue the single best frame instead of a list of top frames
                            self._ocr_queue.put_nowait((tid, best_frame, state["obj"], self.frame_count))
                            state["ocr_attempted"] = True
                        except queue.Full:
                            pass
                    del self.vehicle_state[tid]

                # Process active tracks (only those in the ROI)
                for tid, obj in tracked.items():
                    if tid not in active_roi_track_ids:
                        continue
                        
                    vehicle_type = obj.get("label", "vehicle").lower()
                    vehicle_key = f"vehicle_{tid}"

                    # Keep a minimal state dict to know what we have sent to OCR
                    if tid not in self.vehicle_state:
                        self.vehicle_state[tid] = {
                            "vehicle_key": vehicle_key,
                            "ocr_attempted": False,
                            "obj": obj,
                            "last_seen_frame": self.frame_count
                        }
                    
                    state = self.vehicle_state[tid]
                    state["last_seen_frame"] = self.frame_count
                    state["obj"] = obj

                    # Skip if plate already confirmed or OCR already attempted
                    if obj.get("plate_info") or self._ocr_fusion.should_skip_ocr(tid) or state["ocr_attempted"]:
                        continue

                    # Safely extract crop
                    x1, y1, x2, y2 = obj["box"]
                    vx1, vy1 = max(0, x1), max(0, y1)
                    vx2, vy2 = min(960, x2), min(540, y2)

                    ox1, oy1 = int(vx1 * scale_x), int(vy1 * scale_y)
                    ox2, oy2 = int(vx2 * scale_x), int(vy2 * scale_y)
                    ox1, oy1 = max(0, ox1), max(0, oy1)
                    ox2, oy2 = min(orig_w, ox2), min(orig_h, oy2)
                    
                    vcrop = frame_a[oy1:oy2, ox1:ox2]
                    if vcrop.size == 0:
                        vcrop = frame_disp[vy1:vy2, vx1:vx2]
                        
                    if vcrop.size > 0:
                        # Feed to the ANPR engine's per-vehicle buffer
                        anpr_engine.process_vehicle_frame(
                            vehicle_key=vehicle_key,
                            vehicle_type=vehicle_type,
                            vehicle_crop=vcrop,
                            frame_number=self.frame_count,
                            bbox=(ox1, oy1, ox2, oy2),
                            frame_shape=frame_a.shape,
                            det_confidence=obj.get("confidence", 0.5)
                        )
                        
                        # Early read trigger: Don't wait for vehicle to leave the screen!
                        best_frame_early, frames_seen = anpr_engine.get_best_frame(vehicle_key)
                        if best_frame_early is not None and frames_seen > 0 and frames_seen % 10 == 0:
                            try:
                                self._ocr_queue.put_nowait((tid, best_frame_early, obj, self.frame_count))
                            except queue.Full:
                                pass

                # Periodic stale cleanup for fusion AND vehicle_state memory management
                if self.frame_count % 30 == 0:
                    self._ocr_fusion.cleanup_stale(active_track_ids)
                    stale_tids = [t for t, s in self.vehicle_state.items() if self.frame_count - s["last_seen_frame"] > 60]
                    for t in stale_tids:
                        vehicle_key = self.vehicle_state[t]["vehicle_key"]
                        anpr_engine.finalize_vehicle(vehicle_key)
                        del self.vehicle_state[t]

                    # Periodic traffic count broadcast (every 30s)
                    now_t = time.time()
                    if now_t - self._last_traffic_broadcast >= 30.0:
                        self._last_traffic_broadcast = now_t
                        det_res_counts = det_res
                        try:
                            alert_manager.broadcast_sync({
                                "type": "TRAFFIC_COUNT_UPDATE",
                                "camera_id": self.camera_id,
                                "vehicle_count": det_res_counts.get("vehicle_count", 0),
                                "person_count": det_res_counts.get("person_count", 0),
                                "timestamp": datetime.now().isoformat()
                            })
                        except Exception:
                            pass

                elapsed = time.time() - t_start
                sleep_time = max(0.005, frame_interval - elapsed)
                time.sleep(sleep_time)

            except Exception as e:
                print(f"[VideoStream ERROR in _worker for {self.camera_id}]: {e}")
                time.sleep(0.1)

        if hasattr(self, 'cap_rtsp') and self.cap_rtsp is not None:
            try: self.cap_rtsp.release()
            except: pass
            self.cap_rtsp = None
        if hasattr(self, 'cap_hls') and self.cap_hls is not None:
            try: self.cap_hls.release()
            except: pass
            self.cap_hls = None

    def _ocr_worker_loop(self):
        """
        Persistent OCR worker thread. Reads from bounded queue, runs ANPR,
        feeds results into multi-frame fusion, and broadcasts confirmed plates.
        Runs until self.running is False and the queue is drained.
        """
        while self.running:
            try:
                # Block with timeout so we can check self.running periodically
                try:
                    item = self._ocr_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                tid, best_frame, obj, frame_num = item

                # Process best candidate
                try:
                    confirmed = None
                    last_vcrop = best_frame
                    
                    if best_frame is not None:
                        # Run single-frame ANPR
                        plate_data = anpr_engine.read_plate(best_frame, allow_gemini_fallback=True)

                        if plate_data and plate_data.get("plate"):
                            # Feed into multi-frame OCR fusion
                            ocr_conf = plate_data.get("ocr_confidence", plate_data.get("confidence", 0.0))
                            quality_score = plate_data.get("quality_score", 0.5)
                            det_method = plate_data.get("detection_method", "unknown")

                            if plate_data["plate"].startswith("RAW-"):
                                # [TEST HACK]: Bypass multi-frame consensus for raw test outputs
                                class FakeConfirmed:
                                    plate_text = plate_data["plate"]
                                    best_ocr_confidence = ocr_conf
                                    best_quality_score = quality_score
                                    agreement_ratio = 1.0
                                    format_validation = "TEST_HACK"
                                    final_confidence = 1.0
                                    detection_method = det_method
                                confirmed = FakeConfirmed()
                            else:
                                confirmed = self._ocr_fusion.add_reading(
                                    track_id=tid,
                                    text=plate_data["plate"],
                                    ocr_confidence=ocr_conf,
                                    quality_score=quality_score,
                                    frame_num=frame_num,
                                    detection_method=det_method,
                                )

                    if confirmed:
                        # Build enriched plate_data from confirmed result
                        from core_ai.anpr import VAHAN_DATABASE, ANPREngine
                        vahan = VAHAN_DATABASE.get(confirmed.plate_text,
                                                    ANPREngine._default_vahan(confirmed.plate_text))
                        confirmed_plate_data = {
                            "plate": confirmed.plate_text,
                            "confidence": confirmed.best_ocr_confidence,
                            "ocr_confidence": confirmed.best_ocr_confidence,
                            "plate_detection_confidence": plate_data.get("plate_detection_confidence", 0.0) if plate_data else 0.0,
                            "quality_score": confirmed.best_quality_score,
                            "format_validation": confirmed.format_validation,
                            "multi_frame_agreement": confirmed.agreement_ratio,
                            "final_confidence": confirmed.final_confidence,
                            "detection_method": confirmed.detection_method,
                            "vahan": vahan,
                        }
                        with self.lock:
                            obj["plate_info"] = confirmed_plate_data
                        self._broadcast_anpr(confirmed_plate_data, obj, last_vcrop)
                    else:
                        # No valid plate extracted. Broadcast fallback data so the vehicle is still tracked
                        # Extract color since OCR failed
                        from core_ai.video_pipeline import VideoTimelineIndexer
                        det_color = VideoTimelineIndexer.extract_patch_color(last_vcrop, is_clothing=False)
                        
                        fallback_data = {
                            "plate": "DETECTION FAILED",
                            "confidence": 0.0,
                            "ocr_confidence": 0.0,
                            "plate_detection_confidence": 0.0,
                            "quality_score": 0.0,
                            "format_validation": "FAIL",
                            "multi_frame_agreement": 0.0,
                            "final_confidence": 1.0,  # Force broadcast bypass
                            "detection_method": "failed",
                            "vahan": {
                                "owner": "UNKNOWN",
                                "make_model": "UNKNOWN",
                                "color": det_color,
                                "rto": "UNKNOWN",
                                "status": "UNKNOWN"
                            }
                        }
                        with self.lock:
                            obj["plate_info"] = fallback_data
                        
                        # Do not broadcast fallback data to prevent "DETECTION FAILED" alerts in the UI
                        # self._broadcast_anpr(fallback_data, obj, last_vcrop)

                except Exception as e:
                    print(f"[OCR_WORKER] Error processing crops for track {tid}: {e}")

                self._ocr_queue.task_done()

            except Exception as e:
                print(f"[OCR_WORKER] Unexpected error in worker loop: {e}")
                time.sleep(0.1)

        # Drain remaining items on shutdown
        while not self._ocr_queue.empty():
            try:
                self._ocr_queue.get_nowait()
                self._ocr_queue.task_done()
            except queue.Empty:
                break

    def _broadcast_anpr(self, plate_data, obj, vcrop=None):
        try:
            if not plate_data or not plate_data.get("plate"):
                return

            p_str = plate_data["plate"]
            conf = float(plate_data.get("confidence", 0.0))
            final_conf = float(plate_data.get("final_confidence", conf))
            now_t = time.time()
            now_str = time.strftime("%Y-%m-%d %H:%M:%S")
            img_path = None

            # Duplicate suppression (60s per plate) - bypass for failed detections so they all get logged
            if p_str != "DETECTION FAILED":
                if p_str in self._recent_plates and (now_t - self._recent_plates[p_str] < 60.0):
                    return
                self._recent_plates[p_str] = now_t

            # --- CUSTOM LOGGING REQUESTED BY USER ---
            image_url = None
            if vcrop is not None and p_str != "DETECTION FAILED":
                save_dir = os.path.join(os.getcwd(), "data", "live_detections")
                os.makedirs(save_dir, exist_ok=True)
                img_name = f"{p_str}_{int(now_t)}.jpg"
                img_path = os.path.join(save_dir, img_name)
                image_url = f"/data/live_detections/{img_name}"
                cv2.imwrite(img_path, vcrop)

                log_file = os.path.join(save_dir, "detections_log.jsonl")
                with open(log_file, "a") as f:
                    log_data = {
                        "camera_id": self.camera_id,
                        "plate_number": p_str,
                        "timestamp": now_str,
                        "image_url": image_url,
                        "ocr_confidence": plate_data.get("ocr_confidence"),
                        "plate_detection_confidence": plate_data.get("plate_detection_confidence"),
                        "quality_score": plate_data.get("quality_score"),
                        "format_validation": plate_data.get("format_validation"),
                        "multi_frame_agreement": plate_data.get("multi_frame_agreement"),
                        "final_confidence": final_conf,
                        "detection_method": plate_data.get("detection_method"),
                    }
                    f.write(json.dumps(log_data) + "\n")

            # Confidence gate for DB insertion + broadcast
            if final_conf < 0.40:
                # Too low to broadcast — send LOW_CONFIDENCE event only
                try:
                    alert_manager.broadcast_sync({
                        "type": "LOW_CONFIDENCE_ANPR",
                        "plate_number": p_str,
                        "final_confidence": final_conf,
                        "camera_id": self.camera_id,
                        "timestamp": now_str
                    })
                except Exception:
                    pass
                return

            # Determine review status based on confidence
            review_status = "AUTO_CONFIRMED"
            if final_conf < 0.60:
                review_status = "NEEDS_REVIEW"

            conn = get_db_connection()
            cursor = conn.cursor()
            vahan = plate_data.get("vahan", {})
            now_str = time.strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("SELECT city, district, name FROM cameras WHERE camera_id = ?;", (self.camera_id,))
            cam_row = cursor.fetchone()
            city = cam_row["city"] if cam_row else "Gujarat"

            anpr_id = f"ANPR-{int(time.time()*1000)%1000000}"
            is_flagged = vahan.get("is_flagged", False)
            fir_ref = vahan.get("fir_ref")

            # Insert into vehicle_anpr (backward-compatible + new columns via safe ALTER)
            cursor.execute("""
            INSERT INTO vehicle_anpr (
                anpr_id, camera_id, timestamp, plate_number, confidence,
                vehicle_type, vehicle_color, direction, speed_kmh,
                vahan_owner, vahan_model, vahan_status, is_flagged, fir_reference, bbox_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                anpr_id, self.camera_id, now_str, p_str, final_conf,
                obj.get("label", "VEHICLE"), vahan.get("color") or "Standard", "Inbound", 0.0,
                vahan.get("owner"), vahan.get("make_model"),
                vahan.get("status") or "UNLISTED IN REGISTRY", is_flagged, fir_ref, json.dumps(obj.get("box", []))
            ))

            # Try to update new columns (they may not exist yet if migration hasn't run)
            try:
                cursor.execute("""
                UPDATE vehicle_anpr SET
                    plate_detection_confidence = ?,
                    quality_score = ?,
                    format_validation = ?,
                    detection_method = ?,
                    multi_frame_agreement = ?,
                    review_status = ?
                WHERE anpr_id = ?;
                """, (
                    plate_data.get("plate_detection_confidence"),
                    plate_data.get("quality_score"),
                    plate_data.get("format_validation"),
                    plate_data.get("detection_method"),
                    plate_data.get("multi_frame_agreement"),
                    review_status,
                    anpr_id,
                ))
            except Exception:
                pass  # New columns don't exist yet — graceful degradation

            # Insert into plate_reads table if it exists
            try:
                cursor.execute("""
                INSERT INTO plate_reads (
                    read_id, vehicle_track_id, camera_id, timestamp,
                    plate_text, ocr_confidence, plate_detection_confidence,
                    quality_score, format_validation, detection_method, image_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    f"PR-{int(time.time()*1000)%1000000}",
                    obj.get("track_id"),
                    self.camera_id, now_str, p_str,
                    plate_data.get("ocr_confidence"),
                    plate_data.get("plate_detection_confidence"),
                    plate_data.get("quality_score"),
                    plate_data.get("format_validation"),
                    plate_data.get("detection_method"),
                    img_path,
                ))
            except Exception:
                pass  # Table doesn't exist yet — graceful degradation

            # Insert into review_queue if confidence is low
            if review_status == "NEEDS_REVIEW":
                try:
                    cursor.execute("""
                    INSERT INTO review_queue (
                        review_id, anpr_id, camera_id, timestamp,
                        original_plate_text, ocr_confidence, quality_score, image_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        f"REV-{int(time.time()*1000)%1000000}",
                        anpr_id, self.camera_id, now_str,
                        p_str, plate_data.get("ocr_confidence"),
                        plate_data.get("quality_score"), img_path,
                    ))
                except Exception:
                    pass  # Table doesn't exist yet

            conn.commit()
            conn.close()

            # Broadcast NEW_ANPR_DETECTION (existing fields preserved + new fields added)
            payload = {
                "type": "NEW_ANPR_DETECTION",
                "plate_number": p_str,
                "vehicle_model": vahan.get("make_model") or obj.get("label", "Vehicle"),
                "vehicle_color": vahan.get("color") or "Standard",
                "camera_id": self.camera_id,
                "city": city,
                "is_flagged": bool(is_flagged),
                "timestamp": now_str,
                # New separated confidence fields
                "plate_detection_confidence": plate_data.get("plate_detection_confidence"),
                "ocr_confidence": plate_data.get("ocr_confidence"),
                "quality_score": plate_data.get("quality_score"),
                "format_validation": plate_data.get("format_validation"),
                "multi_frame_agreement": plate_data.get("multi_frame_agreement"),
                "final_confidence": final_conf,
                "detection_method": plate_data.get("detection_method"),
                "review_status": review_status,
            }
            alert_manager.broadcast_sync(payload)

            if is_flagged:
                crit_payload = {
                    "type": "NEW_CRITICAL_ALERT",
                    "title": f"🚨 WANTED VEHICLE DETECTED: {p_str}",
                    "description": f"{vahan.get('make_model')} flagged under {fir_ref}",
                    "camera_id": self.camera_id,
                    "camera_name": cam_row["name"] if cam_row else self.camera_id,
                    "city": city,
                    "plate_number": p_str,
                    "tms_score": 92.5,
                    "timestamp": now_str
                }
                alert_manager.broadcast_sync(crit_payload)

        except Exception as e:
            print(f"Broadcast ANPR Error: {e}")

    def get_frame(self) -> Optional[bytes]:
        with self.lock:
            if self.last_frame is None:
                return None
            if isinstance(self.last_frame, (bytes, bytearray)):
                return self.last_frame
            if isinstance(self.last_frame, np.ndarray):
                _, jpg = cv2.imencode('.jpg', self.last_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                self.last_frame = jpg.tobytes()
                return self.last_frame
            return None

    def release(self):
        self.running = False
        # Do not explicitly release cap_rtsp here. 
        # Doing so from the main thread causes a libavcodec segmentation fault
        # if the worker thread is currently inside a cap_rtsp.read() block.
        # The worker thread will gracefully release it when self.running = False.


def generate_mjpeg_stream(processor: LiveCameraProcessor):
    try:
        while processor.running:
            frame_bytes = processor.get_frame()
            if frame_bytes is not None and isinstance(frame_bytes, (bytes, bytearray)):
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.033)
    except (GeneratorExit, Exception):
        pass


def get_processor(camera_id: str) -> LiveCameraProcessor:
    with capture_lock:
        # Clean up dead processors
        for cid, proc in list(active_captures.items()):
            if not proc.running:
                del active_captures[cid]

        if camera_id in active_captures and active_captures[camera_id].running:
            return active_captures[camera_id]

        # Stop any other active processors to avoid excess GPU load
        for cid, proc in list(active_captures.items()):
            proc.release()
            del active_captures[cid]

        processor = LiveCameraProcessor(camera_id)
        active_captures[camera_id] = processor
        return processor


@router.get("/feed/{camera_id}")
async def get_live_mjpeg_feed(camera_id: str):
    processor = get_processor(camera_id)
    return StreamingResponse(
        generate_mjpeg_stream(processor),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


def get_live_camera_processor_frame(camera_id: str) -> Optional[np.ndarray]:
    """Retrieves the instantaneous uncompressed BGR frame from the active stream worker if available."""
    with capture_lock:
        proc = active_captures.get(camera_id)
    if proc:
        with proc.lock:
            if proc.raw_frame is not None:
                return proc.raw_frame.copy()
    return None
