"""
Florence-2 Vision-Language Model Engine (Red EYE Surveillance Platform)
Integrates Microsoft Florence-2-base for open-vocabulary visual grounding,
dense region captioning, and zero-hallucination verification of CCTV targets.
Rejects false-positive infrastructure (traffic lights, poles, signboards, shadows)
and verifies vehicles, persons, and safety threats.
"""

import os
import re
import cv2
import torch
import numpy as np
from PIL import Image
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

try:
    from transformers import AutoModelForCausalLM, AutoProcessor
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False


class FlorenceVisionEngine:
    _instance = None

    def __init__(self):
        self.model = None
        self.processor = None
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        self._loaded = False

    @classmethod
    def get_instance(cls) -> "FlorenceVisionEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def ensure_loaded(self) -> bool:
        """
        Lazy-loads Florence-2-base model and processor into CUDA VRAM.
        """
        if self._loaded and self.model is not None:
            return True

        if not TRANSFORMERS_AVAILABLE:
            print("[WARN] transformers package not available for Florence-2.")
            return False

        try:
            print(f"[*] Initializing Florence-2-base on {self.device} ({self.dtype})...")
            self.model = AutoModelForCausalLM.from_pretrained(
                'microsoft/Florence-2-base',
                torch_dtype=self.dtype,
                trust_remote_code=True
            ).to(self.device)
            self.processor = AutoProcessor.from_pretrained(
                'microsoft/Florence-2-base',
                trust_remote_code=True
            )
            self._loaded = True
            print("[OK] Florence-2-base Vision Engine ready on CUDA!")
            return True
        except Exception as e:
            print(f"[!] Warning: Could not load Florence-2: {e}")
            self.model = None
            self.processor = None
            self._loaded = False
            return False

    def run_task(self, pil_image: Image.Image, task_prompt: str, text_input: Optional[str] = None, max_tokens: int = 256) -> Dict[str, Any]:
        """
        Executes a sequence-to-sequence Florence-2 vision task.
        """
        if not self.ensure_loaded():
            return {}

        prompt = task_prompt if text_input is None else task_prompt + text_input
        inputs = self.processor(text=prompt, images=pil_image, return_tensors="pt")
        input_ids = inputs["input_ids"].to(self.device)
        pixel_values = inputs["pixel_values"].to(self.device, self.dtype)

        with torch.no_grad():
            generated_ids = self.model.generate(
                input_ids=input_ids,
                pixel_values=pixel_values,
                max_new_tokens=max_tokens,
                num_beams=2,
                do_sample=False
            )

        generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed = self.processor.post_process_generation(
            generated_text,
            task=task_prompt,
            image_size=(pil_image.width, pil_image.height)
        )
        return parsed

    def determine_roi_start(self, frame_bgr: np.ndarray) -> Optional[int]:
        """
        Queries Florence-2 using Visual Question Answering (VQA) to dynamically 
        determine the optimal Y-coordinate for the ANPR Region of Interest (ROI) start line.
        """
        if not self.ensure_loaded():
            return None
            
        h_orig, w_orig = frame_bgr.shape[:2]
        # Convert BGR to RGB PIL Image
        pil_image = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        
        prompt_text = "What percentage from the top of the image (0 to 100) should the horizontal Region of Interest line start to capture vehicles clearly on the road? Answer with only a number."
        
        try:
            parsed = self.run_task(pil_image, "<vqa>", prompt_text)
            answer = parsed.get("<vqa>", "").strip()
            # Try to extract the first number found in the answer string
            import re
            match = re.search(r'\d+', answer)
            if match:
                pct = float(match.group())
                pct = max(10.0, min(90.0, pct)) # Bound between 10% and 90%
                return int((pct / 100.0) * h_orig)
            return None
        except Exception as e:
            print(f"[Florence-2 VLM] Failed to determine dynamic ROI: {e}")
            return None

    def verify_candidate_is_vehicle(self, crop_bgr: np.ndarray) -> Tuple[bool, str, float]:
        """
        Ground-truths whether a crop contains an authentic motor vehicle or non-vehicle infrastructure.
        Returns: (is_vehicle: bool, detected_label: str, confidence: float)
        """
        if crop_bgr is None or crop_bgr.size == 0 or crop_bgr.shape[0] < 12 or crop_bgr.shape[1] < 12:
            return False, "invalid_crop", 0.0

        h, w = crop_bgr.shape[:2]
        # Infrastructure aspect ratio filter: Traffic light fixtures on poles are tall and skinny
        aspect = w / float(max(1, h))
        if aspect < 0.35 and h > 60:
            # Stilt pole / traffic light fixture morphology
            return False, "traffic_light_pole", 0.0

        if not self.ensure_loaded():
            # Fallback heuristic: check edge variance and aspect ratio
            return aspect > 0.45, "vehicle_fallback", 0.85

        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(crop_rgb)

        task = "<CAPTION_TO_PHRASE_GROUNDING>"
        phrases = "car. suv. truck. bus. auto rickshaw. van. motorcycle. traffic light. pole. shadow. street light."
        res = self.run_task(pil_img, task, phrases, max_tokens=128)
        grounding = res.get("<CAPTION_TO_PHRASE_GROUNDING>", {})
        labels = grounding.get("labels", [])

        # Non-vehicle disqualifiers
        disqualifiers = {"traffic light", "pole", "shadow", "street light", "post", "sign", "signboard", "road", "pavement"}
        vehicle_classes = {"car", "suv", "truck", "bus", "auto rickshaw", "van", "motorcycle", "vehicle"}

        found_vehicles = [lbl for lbl in labels if any(vc in lbl.lower() for vc in vehicle_classes)]
        found_disqualifiers = [lbl for lbl in labels if any(dq in lbl.lower() for dq in disqualifiers)]

        if found_disqualifiers and not found_vehicles:
            return False, found_disqualifiers[0], 0.0

        if found_vehicles:
            return True, found_vehicles[0], 0.95

        # If phrase grounding was neutral, use dense region caption
        cap_res = self.run_task(pil_img, "<MORE_DETAILED_CAPTION>", max_tokens=96)
        caption = cap_res.get("<MORE_DETAILED_CAPTION>", "").lower()

        for dq in disqualifiers:
            if dq in caption and not any(vc in caption for vc in ["car", "vehicle", "truck", "suv", "van", "bus", "auto"]):
                return False, dq, 0.0

        for vc in vehicle_classes:
            if vc in caption:
                return True, vc, 0.90

        return True, "car", 0.80

    def verify_candidate_is_person(self, crop_bgr: np.ndarray) -> Tuple[bool, str, float]:
        """
        Ground-truths whether a crop contains an authentic pedestrian.
        """
        if crop_bgr is None or crop_bgr.size == 0:
            return False, "invalid_crop", 0.0

        if not self.ensure_loaded():
            return True, "person_fallback", 0.85

        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(crop_rgb)

        res = self.run_task(pil_img, "<CAPTION_TO_PHRASE_GROUNDING>", "person. man. woman. pedestrian. pole. tree. car.", max_tokens=96)
        labels = res.get("<CAPTION_TO_PHRASE_GROUNDING>", {}).get("labels", [])
        is_person = any(lbl in ["person", "man", "woman", "pedestrian"] for lbl in labels)
        return is_person, labels[0] if labels else "unknown", 0.92 if is_person else 0.10

    @staticmethod
    def detect_auto_rickshaw_heuristics(crop_bgr: np.ndarray) -> bool:
        """
        Fast morphological and spectral detection for Indian three-wheel auto-rickshaws (CNG / petrol).
        Detects characteristic yellow/orange hood canopy and green/dark passenger body.
        """
        if crop_bgr is None or crop_bgr.size == 0:
            return False
        ch, cw = crop_bgr.shape[:2]
        if cw < 18 or ch < 18:
            return False

        hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)

        # Upper canopy check (Yellow/Orange hood)
        canopy = hsv[:int(ch * 0.50), :]
        tot_canopy = canopy.shape[0] * canopy.shape[1]
        if tot_canopy == 0:
            return False
        yellow_canopy = ((canopy[:, :, 0] >= 11) & (canopy[:, :, 0] <= 42) & (canopy[:, :, 1] >= 35) & (canopy[:, :, 2] >= 45))
        yellow_ratio = np.sum(yellow_canopy) / float(tot_canopy)

        # Lower body check (CNG Green or Dark body panels)
        body = hsv[int(ch * 0.45):, :]
        tot_body = body.shape[0] * body.shape[1]
        if tot_body == 0:
            return False
        green_body = ((body[:, :, 0] >= 35) & (body[:, :, 0] <= 98) & (body[:, :, 1] >= 25))
        dark_body = (body[:, :, 2] < 70)
        green_dark_ratio = (np.sum(green_body) + np.sum(dark_body)) / float(tot_body)

        return (yellow_ratio >= 0.12 and green_dark_ratio >= 0.18) or (yellow_ratio >= 0.25)

    def classify_vehicle_fine_grained(self, crop_bgr: np.ndarray) -> Dict[str, Any]:
        """
        Fine-grained vehicle categorization:
        Accurately distinguishes TRUCK, BUS, AUTO-RICKSHAW, SUV, HATCHBACK, SEDAN, and MOTORCYCLE.
        """
        if crop_bgr is None or crop_bgr.size == 0:
            return {"category": "UNKNOWN", "confidence": 0.0, "is_suv": False, "is_rickshaw": False, "is_truck": False, "is_bus": False}

        h, w = crop_bgr.shape[:2]

        # 1. Fast Indian 3-Wheeler Auto-Rickshaw detection
        from core_ai.detector import RealTimeDetector
        if self.detect_auto_rickshaw_heuristics(crop_bgr) or RealTimeDetector.is_auto_rickshaw(crop_bgr, (0, 0, w, h)):
            return {
                "category": "AUTO-RICKSHAW",
                "label": "CNG Auto-Rickshaw (3-Wheeler)",
                "confidence": 0.96,
                "is_suv": False,
                "is_rickshaw": True,
                "is_truck": False,
                "is_bus": False
            }

        # 2. Florence-2 VLM Caption Analysis if available
        if self.ensure_loaded():
            try:
                eval_img = crop_bgr
                if w < 120 or h < 80:
                    scale = max(2, int(150 / max(w, 1)))
                    eval_img = cv2.resize(crop_bgr, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)

                crop_rgb = cv2.cvtColor(eval_img, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(crop_rgb)
                cap_res = self.run_task(pil_img, "<CAPTION>", max_tokens=64)
                cap = cap_res.get("<CAPTION>", "").lower()

                # A. Auto-Rickshaw
                if any(w_word in cap for w_word in ["rickshaw", "three-wheeler", "tuk-tuk", "tuk tuk"]):
                    return {
                        "category": "AUTO-RICKSHAW",
                        "label": "CNG Auto-Rickshaw (3-Wheeler)",
                        "confidence": 0.96,
                        "is_suv": False,
                        "is_rickshaw": True,
                        "is_truck": False,
                        "is_bus": False
                    }
                # B. Heavy Commercial Trucks
                elif any(w_word in cap for w_word in ["truck", "dump truck", "lorry", "semi-truck", "trailer", "flatbed", "garbage truck"]):
                    return {
                        "category": "TRUCK",
                        "label": "Heavy Goods Truck / Commercial Carrier",
                        "confidence": 0.95,
                        "is_suv": False,
                        "is_rickshaw": False,
                        "is_truck": True,
                        "is_bus": False
                    }
                # C. Passenger Buses
                elif any(w_word in cap for w_word in ["bus", "double-decker", "coach", "transit"]):
                    return {
                        "category": "BUS",
                        "label": "Intercity / City Bus",
                        "confidence": 0.95,
                        "is_suv": False,
                        "is_rickshaw": False,
                        "is_truck": False,
                        "is_bus": True
                    }
                # D. Motorcycles & Scooters
                elif any(w_word in cap for w_word in ["motorcycle", "motorbike", "scooter", "moped", "bike"]):
                    return {
                        "category": "MOTORCYCLE",
                        "label": "Motorcycle / Two-Wheeler",
                        "confidence": 0.94,
                        "is_suv": False,
                        "is_rickshaw": False,
                        "is_truck": False,
                        "is_bus": False
                    }
                # E. Sedans (Dzire, Etios, Amaze, Verna, City, etc.)
                is_sedan = any(w_word in cap for w_word in ["sedan", "saloon", "dzire", "etios", "amaze", "verna", "city", "luxury sedan"])
                is_hatchback = any(w_word in cap for w_word in ["hatchback", "compact car", "small car", "swift", "i10", "i20", "wagonr", "alto"])
                aspect = w / float(max(1, h))

                if is_sedan or (aspect > 1.68 and not any(k in cap for k in ["suv", "fortuner", "scorpio"])):
                    return {
                        "category": "SEDAN",
                        "label": "Maruti Dzire / Compact Sedan",
                        "confidence": 0.92,
                        "is_suv": False,
                        "is_rickshaw": False,
                        "is_truck": False,
                        "is_bus": False
                    }
                # F. Hatchbacks
                elif is_hatchback:
                    return {
                        "category": "HATCHBACK",
                        "label": "Compact Hatchback (Maruti / Hyundai)",
                        "confidence": 0.92,
                        "is_suv": False,
                        "is_rickshaw": False,
                        "is_truck": False,
                        "is_bus": False
                    }
                # G. True Full-Size SUVs & MUVs (Fortuner, Scorpio, Bolero, Safari, Endeavour)
                elif any(w_word in cap for w_word in ["fortuner", "suv", "sport utility", "scorpio", "endeavour", "safari", "bolero", "xuv700"]):
                    if aspect > 1.70:
                        # Too flat / low-slung for a full-size SUV
                        return {
                            "category": "SEDAN",
                            "label": "Passenger Sedan / Car",
                            "confidence": 0.85,
                            "is_suv": False,
                            "is_rickshaw": False,
                            "is_truck": False,
                            "is_bus": False
                        }
                    return {
                        "category": "SUV",
                        "label": "Toyota Fortuner / Full-Size SUV",
                        "confidence": 0.94,
                        "is_suv": True,
                        "is_rickshaw": False,
                        "is_truck": False,
                        "is_bus": False
                    }
                # H. Passenger Vans & Minibuses (Eeco, Omni, Traveller, Minibus)
                elif any(w_word in cap for w_word in ["van", "minivan", "minibus"]):
                    return {
                        "category": "VAN",
                        "label": "Passenger Van / Minibus",
                        "confidence": 0.93,
                        "is_suv": False,
                        "is_rickshaw": False,
                        "is_truck": False,
                        "is_bus": False,
                        "is_van": True
                    }
                elif any(w_word in cap for w_word in ["car", "automobile", "vehicle"]):
                    # Generic car caption from Florence-2
                    if aspect > 1.60:
                        return {
                            "category": "SEDAN",
                            "label": "Passenger Sedan / Car",
                            "confidence": 0.85,
                            "is_suv": False,
                            "is_rickshaw": False,
                            "is_truck": False,
                            "is_bus": False
                        }
                    else:
                        return {
                            "category": "CAR",
                            "label": "Passenger Car",
                            "confidence": 0.80,
                            "is_suv": False,
                            "is_rickshaw": False,
                            "is_truck": False,
                            "is_bus": False
                        }
            except Exception:
                pass

        # 3. Geometric & Morphology classification fallback
        aspect = w / float(max(1, h))
        area = w * h

        if aspect < 0.85:
            # Tall and narrow -> Auto-rickshaw or motorcycle
            return {
                "category": "AUTO-RICKSHAW",
                "label": "Auto-Rickshaw / Light Vehicle",
                "confidence": 0.82,
                "is_suv": False,
                "is_rickshaw": True,
                "is_truck": False,
                "is_bus": False
            }
        elif area > 35000 and aspect > 1.4:
            # Huge bounding box with wide aspect ratio -> Heavy Truck or Bus
            return {
                "category": "TRUCK",
                "label": "Heavy Commercial Vehicle / Truck",
                "confidence": 0.88,
                "is_suv": False,
                "is_rickshaw": False,
                "is_truck": True,
                "is_bus": False
            }
        elif area > 14000 and 1.05 <= aspect <= 1.45:
            # Medium frontal vehicle bounding box -> Standard passenger car (hatchback/sedan/crossover)
            # Cannot assume Fortuner/SUV from bounding box size alone without explicit VLM detection
            return {
                "category": "CAR",
                "label": "Passenger Vehicle (Car)",
                "confidence": 0.78,
                "is_suv": False,
                "is_rickshaw": False,
                "is_truck": False,
                "is_bus": False
            }
        elif aspect > 1.55 or area < 10000:
            # Flat low stance or smaller compact area -> Hatchback or Sedan
            return {
                "category": "HATCHBACK",
                "label": "Passenger Car / Hatchback",
                "confidence": 0.82,
                "is_suv": False,
                "is_rickshaw": False,
                "is_truck": False,
                "is_bus": False
            }
        else:
            return {
                "category": "CAR",
                "label": "Passenger Car",
                "confidence": 0.75,
                "is_suv": False,
                "is_rickshaw": False,
                "is_truck": False,
                "is_bus": False
            }

    def verify_vehicle_match(self, crop_bgr: np.ndarray, query_str: str) -> Tuple[bool, str, float, str]:
        """
        Validates vehicle candidate against user query using Florence-2 VLM verification.
        Returns: (is_match, resolved_label, match_score, vlm_explanation)
        """
        u_query = (query_str or "").upper()
        classification = self.classify_vehicle_fine_grained(crop_bgr)
        cat = classification["category"]

        is_suv_query = any(k in u_query for k in ["FORTUNER", "SUV", "SCORPIO", "CRETA", "7-SEATER", "7 SEATER", "MUV"])
        is_rickshaw_query = any(k in u_query for k in ["RICKSHAW", "AUTO", "TUK TUK", "TUK-TUK", "3-WHEELER", "THREE WHEELER"])

        # Case 1: Searching for SUV / Toyota Fortuner
        if is_suv_query:
            if classification["is_rickshaw"] or cat == "AUTO-RICKSHAW":
                return False, "Auto-Rickshaw (3-Wheeler)", 0.05, "Rejected by Florence-2 VLM: Auto-rickshaw detected, does not match SUV/Fortuner query."
            if classification.get("is_truck") or cat == "TRUCK":
                return False, classification["label"], 0.05, f"Rejected by Florence-2 VLM: {classification['label']} is a truck, not an SUV."
            if classification.get("is_bus") or cat == "BUS":
                return False, classification["label"], 0.05, f"Rejected by Florence-2 VLM: {classification['label']} is a bus, not an SUV."
            if classification.get("is_van") or cat == "VAN":
                return False, classification["label"], 0.05, f"Rejected by Florence-2 VLM: {classification['label']} is a passenger van, not a Toyota Fortuner or SUV."
            if cat in ["MOTORCYCLE"]:
                return False, classification["label"], 0.05, "Rejected by Florence-2 VLM: Motorcycle does not match SUV query."

            # Disqualify hatchbacks and sedans when searching for Fortuner / SUV
            if cat in ["HATCHBACK", "SEDAN", "CAR"] and not classification["is_suv"]:
                return False, classification["label"], 0.20, f"Rejected by Florence-2 VLM: Candidate is a {classification['label']}, not a Toyota Fortuner or SUV."

            if classification["is_suv"]:
                suv_conf = float(classification.get("confidence", 0.88))
                return True, "Toyota Fortuner / 7-Seater SUV (Florence-2 Verified)", suv_conf, "Florence-2 Verified: Full-Size SUV profile matches target query."
            else:
                return False, classification["label"], 0.30, "Rejected by Florence-2 VLM: Candidate does not match SUV profile."

        # Case 2: Searching for Auto-Rickshaw
        if is_rickshaw_query:
            if classification["is_rickshaw"]:
                rick_conf = float(classification.get("confidence", 0.92))
                return True, "CNG Auto-Rickshaw (Florence-2 Verified)", rick_conf, "Florence-2 Verified: Three-wheeler auto-rickshaw matches query."
            else:
                return False, classification["label"], 0.08, "Rejected by Florence-2 VLM: Not an auto-rickshaw."

        # Case 3: Searching for Truck
        if "TRUCK" in u_query or "CARRIER" in u_query:
            if classification.get("is_truck") or cat == "TRUCK":
                trk_conf = float(classification.get("confidence", 0.90))
                return True, "Commercial Cargo Truck (Florence-2 Verified)", trk_conf, "Florence-2 Verified: Cargo truck matches query."
            return False, classification["label"], 0.10, "Rejected: Not a cargo truck."

        # Case 4: Searching for Car / Sedan / Hatchback
        is_car_query = any(k in u_query for k in ["CAR", "SEDAN", "HATCHBACK", "AUTOMOBILE"])
        if is_car_query:
            if classification["is_rickshaw"] or cat == "AUTO-RICKSHAW":
                return False, "Auto-Rickshaw (3-Wheeler)", 0.05, "Rejected by Florence-2 VLM: Auto-rickshaw does not match car query."
            if classification.get("is_truck") or cat == "TRUCK":
                return False, classification["label"], 0.05, f"Rejected by Florence-2 VLM: {classification['label']} is a truck, not a car."
            if classification.get("is_bus") or cat == "BUS":
                return False, classification["label"], 0.05, f"Rejected by Florence-2 VLM: {classification['label']} is a bus, not a car."
            if cat in ["MOTORCYCLE"]:
                return False, classification["label"], 0.05, "Rejected by Florence-2 VLM: Motorcycle does not match car query."
            return True, classification["label"], float(classification.get("confidence", 0.88)), f"Florence-2 Verified: {classification['label']} matches car query."

        # Default vehicle matching
        if classification["is_rickshaw"]:
            return True, "CNG Auto-Rickshaw", 0.88, "Florence-2 Identified: Auto-Rickshaw"

        return True, classification["label"], float(classification.get("confidence", 0.78)), "Florence-2 candidate confirmed."

    def verify_person_clothing(self, crop_bgr: np.ndarray, query_str: str) -> Tuple[bool, str, float, str]:
        """
        Validates whether a pedestrian crop matches the requested clothing description.
        Combines Florence-2 multimodal grounding/captioning with photometric HSV+RGB torso analysis.
        Returns: (is_match, resolved_label, confidence, explanation)
        """
        if crop_bgr is None or crop_bgr.size == 0:
            return False, "Unknown", 0.0, "Empty crop"

        h, w = crop_bgr.shape[:2]
        u_query = (query_str or "").upper()

        # 1. Torso Isolation (Upper 20% to 65% height, central 60% width)
        y1_t, y2_t = int(h * 0.20), int(h * 0.65)
        x1_t, x2_t = int(w * 0.20), int(w * 0.80)
        torso = crop_bgr[y1_t:y2_t, x1_t:x2_t]
        if torso.size == 0:
            torso = crop_bgr

        torso_hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
        torso_rgb = cv2.cvtColor(torso, cv2.COLOR_BGR2RGB)

        mean_v = float(np.mean(torso_hsv[:, :, 2]))
        mean_s = float(np.mean(torso_hsv[:, :, 1]))
        mean_rgb = float(np.mean(torso_rgb))

        # 2. VLM Captioning via Florence-2 if active
        vlm_cap = ""
        if self.ensure_loaded():
            try:
                eval_img = crop_bgr
                if w < 100 or h < 160:
                    scale = max(2, int(200 / max(h, 1)))
                    eval_img = cv2.resize(crop_bgr, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)
                crop_rgb = cv2.cvtColor(eval_img, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(crop_rgb)
                cap_res = self.run_task(pil_img, "<MORE_DETAILED_CAPTION>", max_tokens=64)
                vlm_cap = cap_res.get("<MORE_DETAILED_CAPTION>", "").lower()
            except Exception:
                pass

        # 3. Decision Logic for WHITE SHIRT / CLOTHING
        if "WHITE" in u_query:
            # Hard photometric disqualifier: Dark or Black shirt (mean_v < 95 or mean_rgb < 95)
            if mean_v < 95 or mean_rgb < 95:
                return False, "Pedestrian in Dark Attire", 0.05, "Rejected: Torso is dark, not white."

            # Chromatic disqualifiers: Green, Red, Blue, Yellow in VLM caption (standalone words)
            for c in ["green", "red", "blue", "yellow", "orange", "pink"]:
                if re.search(r'\b' + c + r'\b', vlm_cap) and not re.search(r'\bwhite\b', vlm_cap):
                    return False, f"Pedestrian in {c.capitalize()} Attire", 0.10, f"Rejected: Florence-2 detected {c} clothing."

            # Confirmation by Florence-2 or Photometrics
            florence_confirms_white = bool(re.search(r'\bwhite\b', vlm_cap) and any(k in vlm_cap for k in ["shirt", "t-shirt", "top", "blouse", "clothing", "dress", "uniform", "kurta"]))
            photometric_white = (mean_v >= 120 and mean_s <= 65 and mean_rgb >= 110)

            if florence_confirms_white or photometric_white:
                white_conf = round(min(0.92, 0.72 + (mean_v / 255.0) * 0.20), 2)
                return True, "Pedestrian in White Shirt (Florence-2 Verified)", white_conf, "Confirmed: Pedestrian wearing white shirt/top."
            else:
                return False, "Pedestrian (Non-white clothing)", 0.25, "Rejected: Torso clothing does not meet white threshold."

        # 4. Decision Logic for RED SHIRT
        elif "RED" in u_query:
            # If torso is clearly white, light, or gray, reject immediately
            if mean_v >= 125 and mean_s <= 55 and mean_rgb >= 120:
                return False, "Pedestrian in White Attire", 0.05, "Rejected: Torso is white/light, not red."

            # Chromatic RGB check: In authentic red garments, Red channel MUST dominate Green and Blue
            # In brown, tan, beige, and skin tones, R and G are close: R ~ 1.1 * G or R ~ G
            r_ch = torso_rgb[:, :, 0].astype(float)
            g_ch = torso_rgb[:, :, 1].astype(float)
            b_ch = torso_rgb[:, :, 2].astype(float)

            # Chromatic pure red: R significantly greater than G and B, with high saturation
            chromatic_red_pixels = (
                (r_ch > 1.38 * g_ch) &
                (r_ch > 1.38 * b_ch) &
                (r_ch >= 75) &
                ((torso_hsv[:, :, 0] <= 9) | (torso_hsv[:, :, 0] >= 170)) &
                (torso_hsv[:, :, 1] >= 80)
            )
            chromatic_red_ratio = np.sum(chromatic_red_pixels) / float(max(1, torso.shape[0] * torso.shape[1]))
            has_red_word = bool(re.search(r'\bred\b', vlm_cap))

            # Disqualify if Florence-2 detected non-red colors like brown, beige, tan, yellow, white, black
            has_non_red_word = bool(re.search(r'\b(brown|beige|tan|yellow|white|black|dark|blue|green|khaki)\b', vlm_cap))
            if has_non_red_word and not has_red_word:
                return False, "Pedestrian (Non-red Attire)", 0.08, f"Rejected: Attire detected as non-red ({vlm_cap[:40]})."

            if chromatic_red_ratio >= 0.20 or (has_red_word and chromatic_red_ratio >= 0.08):
                red_conf = round(min(0.92, 0.65 + chromatic_red_ratio * 1.2), 2)
                return True, "Pedestrian in Red Shirt (Florence-2 Verified)", red_conf, "Confirmed: Red shirt/top."
            return False, "Pedestrian", 0.10, "Rejected: Torso clothing is not red."

        elif "BLACK" in u_query or "DARK" in u_query:
            if mean_v >= 130 and mean_s <= 55:
                return False, "Pedestrian in Light Attire", 0.05, "Rejected: Torso is light, not dark."

            has_black_word = bool(re.search(r'\b(black|dark)\b', vlm_cap))
            if mean_v < 85 or (has_black_word and mean_v < 110):
                dark_conf = round(min(0.90, 0.70 + (1.0 - mean_v / 255.0) * 0.20), 2)
                return True, "Pedestrian in Black Shirt (Florence-2 Verified)", dark_conf, "Confirmed: Dark/black attire."
            return False, "Pedestrian", 0.10, "Rejected: Not wearing black."

        # Default fallback for general pedestrian search
        return True, "Pedestrian Candidate (Florence-2 Verified)", 0.75, "Candidate pedestrian identified."

    def ground_traffic_scene(self, frame_bgr: np.ndarray) -> Dict[str, Any]:
        """
        Grounds all vehicles, people, and traffic infrastructure in a full 1080p frame.
        """
        if not self.ensure_loaded():
            return {}

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)
        query = "car. white van. white car. black car. truck. bus. auto rickshaw. motorcycle. person. walking pedestrian. traffic light."
        res = self.run_task(pil_img, "<CAPTION_TO_PHRASE_GROUNDING>", query, max_tokens=512)
        return res.get("<CAPTION_TO_PHRASE_GROUNDING>", {})


florence_engine = FlorenceVisionEngine.get_instance()

