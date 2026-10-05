"""
AI Copilot & Crime Intelligence Forensic Engine
Powered by Google Gemini 2.5 Flash API with local rule-based forensic fallback.
Generates automated police dispatch briefs, escape route probability predictions, and interception strategies.
"""

import os
import re
import json
import requests
from typing import Dict, Any, Optional
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/ai", tags=["AI Copilot & Incident Intelligence"])

class GeminiConfigRequest(BaseModel):
    api_key: str

@router.post("/configure_gemini")
def configure_gemini(req: GeminiConfigRequest):
    from core_ai.gemini_vlm import gemini_vision_agent
    if gemini_vision_agent.set_api_key(req.api_key):
        return {"success": True, "message": "Gemini API key configured successfully! Intelligence Engine is now active."}
    return {"success": False, "message": "Invalid API key format. Ensure it is correct."}


def call_gemini_api(prompt_text: str, timeout: float = 6.0) -> Optional[str]:
    """Reusable helper to invoke Google Gemini 2.5 Flash."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt_text}
                ]
            }
        ]
    }
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
        if resp.status_code == 200:
            res_json = resp.json()
            return res_json["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        pass
    return None


class IncidentAnalysisRequest(BaseModel):
    plate_number: str
    vehicle_model: str
    vehicle_color: str
    fir_reference: Optional[str] = None
    last_camera_id: str
    last_camera_name: str
    city: str
    speed_kmh: float
    direction: str
    evidence_confidence: float


def generate_local_fallback_intelligence(data: IncidentAnalysisRequest) -> Dict[str, Any]:
    """Robust local forensic intelligence generator when network or Gemini API is unreachable."""
    return {
        "status": "SUCCESS (LOCAL FORENSIC ENGINE FALLBACK)",
        "source": "PhantomEye Embedded Intelligence Matrix",
        "threat_level": "CRITICAL THREAT",
        "threat_assessment": f"Target vehicle {data.plate_number} ({data.vehicle_color} {data.vehicle_model}) sighted at {data.last_camera_name} ({data.city}) traveling {data.direction} at {data.speed_kmh:.1f} km/h with {data.evidence_confidence*100:.1f}% evidence confidence.",
        "probable_escape_corridor": f"NH-48 Outbound towards {data.city} Highway Checkposts / Outer Ring Road",
        "intercept_strategy": [
            f"Deploy Highway Interception Squad to block downstream junction ahead of {data.last_camera_name}.",
            "Coordinate with Regional Border Toll Plazas for selective lane closure.",
            "Broadcast immediate high-priority APB alert to field PCR vans with target description."
        ],
        "control_room_dispatch_message": f"ALL UNITS: INTERCEPT WANTED {data.vehicle_color.upper()} {data.vehicle_model.upper()} ({data.plate_number}) PASSING {data.last_camera_name.upper()} AT {data.speed_kmh:.0f} KM/H."
    }


def sanitize_input(text: str) -> str:
    if not text: return ""
    # Strip dangerous characters, allow basic alphanumeric and punctuation
    cleaned = re.sub(r'[^\w\s\-\.,]', '', str(text))
    return cleaned[:100]

@router.post("/analyze-incident")
def analyze_incident(req: IncidentAnalysisRequest):
    plate = sanitize_input(req.plate_number)
    color = sanitize_input(req.vehicle_color)
    model = sanitize_input(req.vehicle_model)
    fir = sanitize_input(req.fir_reference or 'eGujCop Wanted Database')
    camera = sanitize_input(req.last_camera_name)
    city = sanitize_input(req.city)
    direction = sanitize_input(req.direction)
    cam_id = sanitize_input(req.last_camera_id)

    prompt = f"""
You are the Tactical AI Intelligence Officer in the Gujarat Police CSITMS Command Center.
A suspect vehicle has just been detected by CCTV AI surveillance.

VEHICLE TELEMETRY:
- Target Plate: {plate}
- Make / Model: {color} {model}
- FIR / Crime Case: {fir}
- Last Sighting Node: {camera} ({cam_id}) in {city}
- Transit Direction: {direction}
- Speed: {req.speed_kmh} km/h
- AI Evidence Confidence: {req.evidence_confidence * 100:.1f}%

TASK:
Provide a concise, professional police tactical brief in valid JSON format with exactly these keys:
{{
  "threat_level": "CRITICAL THREAT",
  "threat_assessment": "Short 2-sentence situational assessment",
  "probable_escape_corridor": "Predicted highway or escape direction",
  "intercept_strategy": [
    "Action item 1",
    "Action item 2",
    "Action item 3"
  ],
  "control_room_dispatch_message": "Immediate radio broadcast message for PCR field units"
}}
Return ONLY valid JSON.
"""

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    try:
        resp = requests.post(GEMINI_URL, json=payload, timeout=6.0)
        if resp.status_code == 200:
            res_json = resp.json()
            raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
            clean_text = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            ai_data = json.loads(clean_text)
            ai_data["status"] = "SUCCESS (LIVE GOOGLE GEMINI 2.5 FLASH)"
            ai_data["source"] = "Google Gemini 2.5 Flash Cloud AI"
            return ai_data
        else:
            print(f"[!] Gemini HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[!] Gemini API request failed ({e}), switching to local forensic fallback...")

    return generate_local_fallback_intelligence(req)


class VLMScanRequest(BaseModel):
    camera_id: str = "CAM-005"
    image_base64: Optional[str] = None


class GeminiConfigRequest(BaseModel):
    api_key: str


@router.get("/gemini_status")
def get_gemini_status():
    import torch
    from core_ai.gemini_vlm import gemini_vlm
    is_conf = gemini_vlm.is_configured()
    return {
        "configured": is_conf,
        "engine": "Gemini 2.5 Flash (Cloud VLM)" if is_conf else "Microsoft Florence-2 (Local CUDA VLM)",
        "cuda_available": torch.cuda.is_available(),
        "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    }


@router.post("/configure_gemini")
def configure_gemini(req: GeminiConfigRequest):
    from core_ai.gemini_vlm import gemini_vlm
    success = gemini_vlm.set_api_key(req.api_key)
    return {
        "success": success,
        "message": "Gemini API key configured and activated successfully!" if success else "Invalid API key provided.",
        "engine": "Gemini 2.5 Flash (Cloud VLM)" if success else "Microsoft Florence-2 (Local CUDA VLM)"
    }


@router.post("/vlm_scan")
def run_vlm_scan(req: VLMScanRequest):
    import cv2
    import numpy as np
    from pathlib import Path
    from core_ai.gemini_vlm import gemini_vlm
    from backend.routers.video_stream import get_processor

    frame_bgr = None
    cam_id = req.camera_id

    # 0. If direct image provided via base64
    if req.image_base64:
        try:
            import base64
            b64_data = req.image_base64
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            raw_bytes = base64.b64decode(b64_data)
            nparr = np.frombuffer(raw_bytes, np.uint8)
            frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception as e:
            print("[WARN] Error decoding image_base64:", e)

    # 1. Try to get current live frame from camera processor
    if frame_bgr is None:
        try:
            from backend.routers.video_stream import get_processor
            proc = get_processor(cam_id)
            with proc.lock:
                if proc.last_frame:
                    nparr = np.frombuffer(proc.last_frame, np.uint8)
                    frame_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            # 2. If no processor frame yet, read 1 frame from source
            if frame_bgr is None:
                source_url = proc.stream_source
                cap = cv2.VideoCapture(source_url)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        frame_bgr = frame
                    cap.release()
        except Exception as err:
            print("[WARN] Error getting processor frame:", err)

    # 3. Fallback to sample feed
    if frame_bgr is None:
        sample_p = Path("frontend/static/assets/sample_feed.jpg")
        if sample_p.exists():
            frame_bgr = cv2.imread(str(sample_p))

    if frame_bgr is None:
        return {"error": f"Could not capture frame from {cam_id}"}

    # Run Gemini analysis if configured
    if gemini_vlm.is_configured():
        res = gemini_vlm.analyze_cctv_frame(frame_bgr, camera_name=cam_id)
        if not res.get("error"):
            return res

    # Fallback to local Florence-2 (RTX 3060 CUDA)
    try:
        from core_ai.vlm_engine import Florence2VLM
        if not hasattr(run_vlm_scan, "_florence"):
            run_vlm_scan._florence = Florence2VLM()
        florence = run_vlm_scan._florence

        caption = florence.generate_caption(frame_bgr)
        grounding = florence.dense_grounding(frame_bgr)

        vehicles = []
        people = []
        for g in grounding:
            lbl = g["label"].lower()
            if any(w in lbl for w in ["car", "bus", "truck", "motorcycle", "vehicle", "van", "tuk-tuk", "rickshaw"]):
                vtype = "Auto-Rickshaw" if ("tuk-tuk" in lbl or "rickshaw" in lbl) else ("Bus" if "bus" in lbl else ("Truck" if "truck" in lbl else "Car/SUV"))
                vehicles.append({
                    "type": vtype,
                    "make_model": lbl.title(),
                    "color": "Visual Grounding",
                    "plate_number": "Scanned at Bumper",
                    "details": f"Region {g['box']}"
                })
            elif any(w in lbl for w in ["person", "man", "woman", "pedestrian", "driver"]):
                people.append({
                    "role": "Subject",
                    "upper_clothing": lbl.title(),
                    "lower_clothing": "Nominal",
                    "helmet": None
                })

        return {
            "configured": False,
            "engine": "Microsoft Florence-2 (Local CUDA VLM)",
            "scene_summary": caption,
            "vehicles": vehicles[:8],
            "people": people[:8],
            "overall_threat_level": "NOMINAL",
            "traffic_anomalies": []
        }
    except Exception as e:
        return {
            "error": str(e),
            "engine": "Error fallback"
        }
