"""
Gemini Multimodal Vision Engine for CCTV Forensics
Provides advanced vehicle make/model recognition, clothing classification,
and low-resolution/angled Indian license plate decoding using Google Gemini.
"""

import os
import cv2
import json
import base64
from pathlib import Path
from typing import Dict, Optional, Any

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


class GeminiVisionEngine:
    _instance = None

    def __init__(self):
        self.api_key = self._load_api_key()
        self.client = None
        self._quota_backoff_until = 0.0
        self._init_client()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_available(self) -> bool:
        import time
        if not self.is_configured():
            return False
        if time.time() < self._quota_backoff_until:
            return False
        return True

    def mark_quota_exhausted(self, retry_after_sec: float = 60.0):
        import time
        self._quota_backoff_until = time.time() + retry_after_sec

    def _load_api_key(self) -> Optional[str]:
        # 1. Environment variable
        key = os.environ.get("GEMINI_API_KEY")
        if key and len(key.strip()) > 10:
            return key.strip()

        # 2. Local .env file
        env_paths = [
            Path(".env"),
            Path("data/.env")
        ]
        for p in env_paths:
            if p.exists():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.startswith("GEMINI_API_KEY="):
                                k = line.split("=", 1)[1].strip().strip('"').strip("'")
                                if len(k) > 10:
                                    return k
                except Exception:
                    pass
        return None

    def _init_client(self):
        if not GENAI_AVAILABLE or not self.api_key:
            self.client = None
            return
        try:
            self.client = genai.Client(api_key=self.api_key)
            print("[OK] Google Gemini Vision Client initialized successfully!")
        except Exception as e:
            print("[WARN] Failed to initialize Google Gemini Client:", e)
            self.client = None

    def set_api_key(self, api_key: str) -> bool:
        clean_key = api_key.strip()
        if len(clean_key) < 15:
            return False
        self.api_key = clean_key
        os.environ["GEMINI_API_KEY"] = clean_key

        # Persist to local .env
        env_file = Path(".env")
        try:
            lines = []
            if env_file.exists():
                with open(env_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            
            with open(env_file, "w", encoding="utf-8") as f:
                key_written = False
                for line in lines:
                    if line.startswith("GEMINI_API_KEY="):
                        f.write(f"GEMINI_API_KEY={clean_key}\n")
                        key_written = True
                    else:
                        f.write(line)
                if not key_written:
                    f.write(f"GEMINI_API_KEY={clean_key}\n")
        except Exception as e:
            print(f"[WARN] Failed to write API key to .env: {e}")
            pass

        self._init_client()
        return self.client is not None

    def is_configured(self) -> bool:
        return self.client is not None

    def analyze_cctv_frame(self, frame_bgr, camera_name: str = "CCTV Camera") -> Dict[str, Any]:
        """
        Runs comprehensive multimodal forensic scene analysis.
        Returns vehicle makes/models, license plates, people attire, and traffic threats.
        """
        if not self.is_configured():
            return {
                "configured": False,
                "engine": "Local Florence-2 / YOLOv8",
                "message": "Gemini API key not configured. Add GEMINI_API_KEY in settings to activate Gemini Vision."
            }

        # Encode frame to JPEG
        _, buffer = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
        image_bytes = buffer.tobytes()

        prompt = f"""
You are an expert Indian Traffic Police Surveillance AI examining a 1080p CCTV camera feed ({camera_name}).
Analyze this image thoroughly with extreme precision. Focus on:
1. VEHICLES:
   - Identify specific vehicle type (e.g. Auto-Rickshaw, 7-Seater SUV, Hatchback, Heavy Truck, GSRTC/Intercity Bus, Motorcycle/Scooter).
   - Identify exact make & model if discernible (e.g. Bajaj Compact RE, Toyota Fortuner, Mahindra Scorpio, Tata 407, Ashok Leyland Bus, Maruti Swift, Honda Activa).
   - Body color and distinguishing commercial markings or rooftop carriers.
   - Any visible Indian license plates (e.g. GJ-01-..., GJ-27-..., GJ-18-..., MH-..., RJ-...). Note both 1-line and 2-line plates (Yellow commercial or White private).
2. PEOPLE:
   - Clothing details: Upper garment color and type (e.g. White shirt, Blue T-shirt, Kurta, Khaki uniform).
   - Lower garment color and type (e.g. Blue jeans, Black trousers, White dhoti).
   - Safety gear: Helmet present or missing on two-wheelers.
3. TRAFFIC & SAFETY ANOMALIES:
   - Jaywalking, lane obstruction, high congestion, red light transit, wrong-way driving.

Output strictly valid JSON with this exact schema:
{{
  "scene_summary": "Brief 1-2 sentence description",
  "vehicles": [
    {{
      "type": "Auto-Rickshaw | SUV | Bus | Truck | Motorcycle | Car",
      "make_model": "e.g. Bajaj RE / Toyota Fortuner / Tata Truck",
      "color": "Primary color",
      "plate_number": "Decoded plate or UNKNOWN",
      "plate_type": "Yellow Commercial | White Private | Green EV | Not Visible",
      "details": "Notable features (carrier, graphics, cargo)"
    }}
  ],
  "people": [
    {{
      "role": "Driver | Passenger | Pedestrian",
      "upper_clothing": "e.g. White Shirt",
      "lower_clothing": "e.g. Blue Jeans",
      "helmet": true
    }}
  ],
  "traffic_anomalies": ["list of observable infractions or hazards, or empty"],
  "overall_threat_level": "NOMINAL | LOW | MEDIUM | HIGH"
}}
"""
        try:
            response, active_model = self._generate_content_resilient(
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                    prompt
                ],
                response_mime_type='application/json'
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            data = json.loads(raw_text.strip())
            data["configured"] = True
            data["engine"] = f"Google Gemini ({active_model})"
            return data
        except Exception as e:
            return {
                "configured": True,
                "engine": "Gemini 2.5 Flash",
                "error": str(e)
            }

    def decode_license_plate(self, crop_bgr) -> Optional[Dict[str, Any]]:
        """
        Specialized decoding for Indian vehicle license plates via Gemini Flash Vision.
        Strictly returns null if plate is blurry, distant, or unreadable to prevent false approximations.
        """
        if not self.is_available() or crop_bgr is None or crop_bgr.size == 0:
            return None

        # Upscale crop if small to help vision model
        h, w = crop_bgr.shape[:2]
        if w < 160 or h < 80:
            scale = max(2, int(200 / max(w, 1)))
            crop_bgr = cv2.resize(crop_bgr, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)

        _, buffer = cv2.imencode('.jpg', crop_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
        image_bytes = buffer.tobytes()

        prompt = """
You are a forensic OCR engine specializing in Indian Vehicle License Plates for Police Surveillance.
Examine this vehicle/plate crop with utmost precision.
Indian plates follow standard formats such as:
- Standard: GJ 01 AB 1234, GJ 27 AX 9999, GJ 18 ZZ 7777, GJ 05 CD 5678, GJ 27 E 5539
- Bharat Series: 22 BH 1234 AA

CRITICAL ACCURACY DIRECTIVES:
- If NO license plate is clearly readable, or if the text is blurry, distant, low-contrast, dark, or ambiguous, you MUST set "plate_number": null and "confidence": 0.0.
- STRICTLY DO NOT GUESS, APPROXIMATE, OR HALLUCINATE NUMBERS OR LETTERS.
- If and only if the plate is 100% legibly readable, output the cleaned alphanumeric string without spaces or dashes (e.g. "GJ01AB1234").

Output ONLY a JSON object:
{
  "plate_number": "GJ01AB1234" or null,
  "confidence": 0.95,
  "plate_color": "Yellow Commercial | White Private | null",
  "raw_text": "Exact text visible or null"
}
"""
        try:
            response, active_model = self._generate_content_resilient(
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                    prompt
                ],
                response_mime_type='application/json'
            )
            raw = response.text.strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            data = json.loads(raw.strip())
            p_num = data.get("plate_number")
            if not p_num or str(p_num).lower() in ["null", "none", "n/a", ""]:
                return None
            return data
        except Exception:
            return None

    def determine_roi_start(self, frame_bgr, camera_name: str = "CCTV Camera") -> Optional[int]:
        """
        Sends a single frame to Gemini Vision to dynamically determine the optimal
        Y-coordinate for the ANPR Region of Interest (ROI) start line.
        """
        if not self.is_configured():
            return None
            
        h_orig, w_orig = frame_bgr.shape[:2]
        _, buffer = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        image_bytes = buffer.tobytes()

        prompt = f"""
You are a traffic camera calibration AI analyzing a CCTV frame from {camera_name}.
We need to set a horizontal "Region of Interest (ROI) Start Line" across the screen.
- Vehicles ABOVE this line are too far away (small, blurry) and should be ignored.
- Vehicles BELOW this line are close enough to the camera to reliably read their license plates.
Determine the optimal percentage from the TOP of the image (0 to 100) where this line should be placed.
For example, if the road starts in the middle, it might be 50. If the camera points down, it might be 20.
Output ONLY a JSON object:
{{
  "roi_start_percentage": 65
}}
"""
        try:
            response, _ = self._generate_content_resilient(
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                    prompt
                ],
                response_mime_type='application/json'
            )
            raw = response.text.strip()
            if raw.startswith("```json"): raw = raw[7:]
            if raw.startswith("```"): raw = raw[3:]
            if raw.endswith("```"): raw = raw[:-3]
            data = json.loads(raw.strip())
            pct = float(data.get("roi_start_percentage", 65))
            pct = max(10.0, min(90.0, pct)) # Bound between 10% and 90%
            return int((pct / 100.0) * h_orig)
        except Exception as e:
            print(f"[Gemini VLM] Failed to determine dynamic ROI: {e}")
            return None

    CANDIDATE_MODELS = [
        'gemini-3.1-flash-lite',
        'gemini-3-flash-preview',
        'gemini-flash-latest',
        'gemini-2.5-flash',
    ]

    def _generate_content_resilient(self, contents, response_mime_type: Optional[str] = None):
        """
        Executes generate_content across a cascade of Gemini Flash models.
        Automatically falls back to next available model if one returns 429 quota or 503 unavailable.
        """
        last_error = "No models attempted"
        for m in self.CANDIDATE_MODELS:
            try:
                config = None
                if response_mime_type:
                    config = types.GenerateContentConfig(response_mime_type=response_mime_type)
                resp = self.client.models.generate_content(
                    model=m,
                    contents=contents,
                    config=config
                )
                if resp and resp.text:
                    return resp, m
            except Exception as e:
                err_str = str(e)
                last_error = err_str
                # Try next model if quota exhausted or service temporarily unavailable
                if any(err_code in err_str for err_code in ["429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "404"]):
                    continue
                else:
                    break

        if "429" in last_error or "RESOURCE_EXHAUSTED" in last_error:
            self.mark_quota_exhausted(60.0)
        raise RuntimeError(f"All Gemini models exhausted: {last_error}")

    def verify_vehicle_with_gemini(self, crop_bgr, target_description: str) -> Dict[str, Any]:
        """
        Forensic Vehicle Make & Model Verification via Gemini Flash Vision API.
        Accurately identifies SUV, Hatchback, Sedan, Truck, Bus, Auto-Rickshaw, and exact model.
        """
        if not self.is_available() or crop_bgr is None or crop_bgr.size == 0:
            return {"is_match": False, "confidence": 0.0, "reason": "Gemini not available or in quota backoff"}

        h, w = crop_bgr.shape[:2]
        eval_crop = crop_bgr
        if w < 160 or h < 120:
            scale = max(2, int(220 / max(w, h, 1)))
            eval_crop = cv2.resize(crop_bgr, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)

        _, buffer = cv2.imencode('.jpg', eval_crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        image_bytes = buffer.tobytes()

        prompt = f"""
You are an expert Indian Traffic Forensic Police AI examining a vehicle crop from CCTV.
Target Search Query: "{target_description}"

Carefully analyze this vehicle image:
1. Identify vehicle category: (SUV | Hatchback | Sedan | Auto-Rickshaw | Heavy Truck | Bus | Motorcycle / Two-Wheeler | Delivery Van / Minibus).
2. Discern exact Make & Model if visible (e.g. Toyota Fortuner, Mahindra Scorpio, Maruti Swift, Maruti Dzire, Hyundai Creta, Tata 407, Ashok Leyland Bus, Bajaj Compact).
3. Identify dominant vehicle body color (White, Black, Blue, Silver, Grey, Red, Green, Yellow).
4. Determine if this vehicle matches the target query "{target_description}":
   - If query searches for a general category and color (e.g. "black car", "white car", "red car", "silver suv", "truck"):
     * If the vehicle is of that category (e.g. car / sedan / hatchback / SUV) and has matching dominant color (e.g. black / dark for "black car", white / silver for "white car"), confirm is_match = true!
     * Do not require legible badge text on distant CCTV crops as long as vehicle body category and color match.
     * CRITICAL RULE: An Auto-Rickshaw (3-Wheeler / CNG / Tuk-Tuk) is NEVER a Car, Sedan, Hatchback, or SUV! If query specifies "car", "suv", "sedan", or "hatchback", an Auto-Rickshaw is strictly is_match = false!
   - If query searches for specific "Toyota Fortuner" or "SUV" or "7-Seater":
     * A Hatchback (e.g. Swift, WagonR), Sedan (e.g. Dzire, Etios), Truck, Van (Eeco/Omni), Bus, or Auto-Rickshaw is strictly is_match = false!
     * Only true Full-Size or Mid-Size SUVs (Fortuner, Scorpio, Endeavour, Bolero, Safari, Creta) can be is_match = true.
   - If query specifies a color (e.g. "Black"), a White, Silver, Bright Red, or Yellow vehicle is strictly is_match = false!
5. Real Confidence Score:
   - Provide an honest probabilistic confidence score between 0.05 and 0.98.
   - If it is a solid category and color match, return confidence 0.82 to 0.94.
   - If it is definitely NOT a match, return confidence < 0.20.

Output strictly valid JSON with keys:
{{
  "is_match": true,
  "vehicle_class": "SUV",
  "detected_model": "Toyota Fortuner",
  "detected_color": "White",
  "confidence": 0.88,
  "reason": "Brief forensic explanation"
}}
"""
        import concurrent.futures
        def _call_gemini():
            response, active_model = self._generate_content_resilient(
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                    prompt
                ],
                response_mime_type='application/json'
            )
            raw = response.text.strip()
            data = json.loads(raw)
            conf = float(data.get("confidence", 0.5))
            return {
                "is_match": bool(data.get("is_match", False)),
                "vehicle_class": data.get("vehicle_class", "Vehicle"),
                "detected_model": data.get("detected_model", "Vehicle"),
                "detected_color": data.get("detected_color", "Unknown"),
                "confidence": conf,
                "reason": data.get("reason", ""),
                "active_model": active_model
            }

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_call_gemini)
                return fut.result(timeout=5.0)
        except concurrent.futures.TimeoutError:
            return {"is_match": False, "confidence": 0.0, "reason": "Gemini API call timed out after 5.0s"}
        except Exception as e:
            err_msg = str(e)
            if any(k in err_msg for k in ["429", "RESOURCE_EXHAUSTED"]):
                self.mark_quota_exhausted(60.0)
            return {"is_match": False, "confidence": 0.0, "reason": err_msg}

    def verify_person_clothing_with_gemini(self, crop_bgr, target_description: str) -> Dict[str, Any]:
        """
        Forensic Pedestrian Attire Verification via Gemini Flash Vision API.
        Accurately identifies upper garment color, type, lower color, and matches against query.
        """
        if not self.is_available() or crop_bgr is None or crop_bgr.size == 0:
            return {"is_match": False, "confidence": 0.0, "reason": "Gemini not available or in quota backoff"}

        h, w = crop_bgr.shape[:2]
        eval_crop = crop_bgr
        if w < 120 or h < 200:
            scale = max(2, int(260 / max(w, 1)))
            eval_crop = cv2.resize(crop_bgr, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)

        _, buffer = cv2.imencode('.jpg', eval_crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        image_bytes = buffer.tobytes()

        prompt = f"""
You are an expert Indian Forensic Surveillance AI examining a pedestrian crop from CCTV.
Target Clothing Query: "{target_description}"

Carefully analyze the pedestrian's attire:
1. Upper clothing color (e.g. White, Red, Blue, Green, Black, Yellow, Brown, Beige, etc.).
2. Upper clothing type (e.g. Shirt, T-Shirt, Kurta, Jacket, Uniform, Saree, Blouse).
3. Lower clothing color and type (e.g. Black trousers, Blue jeans, White dhoti, etc.).
4. Does this pedestrian match the target query "{target_description}"?
   - If query specifies "white shirt": A red shirt, green top, blue shirt, dark uniform, brown/beige kurta, or jacket is strictly is_match = false!
   - If query specifies "red shirt": A white shirt, blue shirt, brown/beige kurta, yellow top, or dark uniform is strictly is_match = false!
5. Real Confidence Score:
   - Provide an honest probabilistic confidence score between 0.05 and 0.98.
   - If it does NOT match, confidence must be < 0.20.

Output strictly valid JSON with keys:
{{
  "is_match": true,
  "upper_color": "White",
  "upper_type": "Shirt",
  "lower_color": "Black",
  "confidence": 0.90,
  "reason": "Brief forensic explanation"
}}
"""
        import concurrent.futures
        def _call_gemini_person():
            response, active_model = self._generate_content_resilient(
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                    prompt
                ],
                response_mime_type='application/json'
            )
            raw = response.text.strip()
            data = json.loads(raw)
            conf = float(data.get("confidence", 0.5))
            return {
                "is_match": bool(data.get("is_match", False)),
                "upper_color": data.get("upper_color", "Unknown"),
                "upper_type": data.get("upper_type", "Garment"),
                "lower_color": data.get("lower_color", "Unknown"),
                "confidence": conf,
                "reason": data.get("reason", ""),
                "active_model": active_model
            }

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_call_gemini_person)
                return fut.result(timeout=5.0)
        except concurrent.futures.TimeoutError:
            return {"is_match": False, "confidence": 0.0, "reason": "Gemini API call timed out after 5.0s"}
        except Exception as e:
            err_msg = str(e)
            if any(k in err_msg for k in ["429", "RESOURCE_EXHAUSTED"]):
                self.mark_quota_exhausted(60.0)
            return {"is_match": False, "confidence": 0.0, "reason": err_msg}

    def detect_realtime_crime_with_gemini(self, frame_bgr, camera_name: str = "Live CCTV Node") -> Dict[str, Any]:
        """
        Exclusively detects real-time crimes and critical incidents from live camera stream frames:
        1. PHYSICAL_ALTERCATION: People fighting, brawling, grappling, or engaging in violent assault.
        2. WEAPON_DETECTED: Persons wielding, brandishing, or carrying firearms, knives, swords, blades, or lethal weapons.
        3. ROAD_COLLISION: Active road accident, vehicular impact/crash, overturned vehicle, or vehicle-pedestrian impact.
        STRICTLY excludes ordinary traffic, pedestrian walking, speed violations, red lights, or non-emergencies.
        """
        if not self.is_configured():
            return {
                "detected": False,
                "category": "NONE",
                "confidence": 0.0,
                "reason": "Gemini Vision not configured."
            }

        h, w = frame_bgr.shape[:2]
        # Resize to max 1280 wide to keep upload snappy and sub-second
        if w > 1280:
            scale = 1280.0 / w
            frame_eval = cv2.resize(frame_bgr, (1280, int(h * scale)))
        else:
            frame_eval = frame_bgr

        _, buffer = cv2.imencode('.jpg', frame_eval, [cv2.IMWRITE_JPEG_QUALITY, 85])
        image_bytes = buffer.tobytes()

        prompt = f"""
You are the Real-Time Tactical Incident & Crime Sentry for Gujarat Police Command & Control ({camera_name}).
Examine this live CCTV surveillance frame STRICTLY AND EXCLUSIVELY for the following THREE CRITICAL SITUATIONS ONLY:
1. PHYSICAL_ALTERCATION: Active physical fight, brawl, grappling, punching, kicking, or violent public assault.
2. WEAPON_DETECTED: Person brandishing, holding, or carrying a weapon (firearm/gun, knife, sword, machete, club, or lethal weapon).
3. ROAD_COLLISION: Active road accident, vehicle crash, vehicular collision, overturned vehicle, or car-pedestrian impact.

STRICT OPERATIONAL RULES:
- If NONE of these 3 specific emergencies are present, you MUST set "detected": false and "category": "NONE".
- Do NOT flag normal traffic, normal pedestrians, people walking near each other, normal conversation, traffic stopping at signals, or minor parking.
- Only return "detected": true if you have genuine visual evidence of one of the THREE target events.

Return strictly valid JSON with this exact schema:
{{
  "detected": true or false,
  "category": "PHYSICAL_ALTERCATION" or "WEAPON_DETECTED" or "ROAD_COLLISION" or "NONE",
  "title": "Concise event title (e.g. 'Physical Altercation / Public Violence in Progress' or 'Armed Subject / Weapon Brandishing' or 'Major Vehicle Collision / Carriageway Impact')",
  "confidence": 0.0 to 1.0,
  "threat_level": "CRITICAL" or "HIGH" or "NONE",
  "bbox": [ymin, xmin, ymax, xmax] or null,
  "observable_evidence": [
    "Specific visual indicator 1 observed in this frame",
    "Specific visual indicator 2 observed in this frame",
    "Specific visual indicator 3 observed in this frame"
  ],
  "timeline": {{
    "t_minus_10s": "Pre-event condition",
    "t_impact_0s": "Incident impact / event occurrence observed on feed",
    "t_plus_10s": "Post-event situation requiring immediate emergency dispatch"
  }},
  "recommended_dispatch": "Specific emergency unit to dispatch (e.g. 'Dispatch Beat Patrol PCR Van 02 + Armed Station Police' or 'Dispatch 108 Emergency Ambulance + Traffic Police Interceptor')"
}}
"""
        try:
            response, active_model = self._generate_content_resilient(
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                    prompt
                ],
                response_mime_type='application/json'
            )
            raw = response.text.strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            data = json.loads(raw.strip())
            data["active_model"] = active_model
            return data
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                self.mark_quota_exhausted(60.0)
            return {
                "detected": False,
                "category": "NONE",
                "confidence": 0.0,
                "reason": err_msg
            }


gemini_vlm = GeminiVisionEngine.get_instance()

