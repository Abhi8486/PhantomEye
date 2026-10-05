"""
GPU-Accelerated Object & Threat Detector
Uses YOLO26 with TensorRT/CUDA optimization for high-accuracy inference on RTX 3060.
"""

import torch
import cv2
import numpy as np
from ultralytics import YOLO


class RealTimeDetector:
    def __init__(self, model_name="yolo26s.pt", conf_thresh=0.25, iou_thresh=0.45):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[*] Initializing YOLO26 Detector on {self.device.upper()} ({model_name})...")
        self.model = YOLO(model_name)
        self.conf_thresh = conf_thresh
        self.iou_thresh = iou_thresh
        self.threat_classes = {"knife", "scissors", "gun", "dagger", "sword", "baseball bat"}
        self.vehicle_classes = {"car", "motorcycle", "bus", "truck"}
        print(f"[OK] YOLO26 Detector ({model_name}) Ready on {self.device.upper()}!")

    @staticmethod
    def is_auto_rickshaw(frame_bgr, box):
        x1, y1, x2, y2 = box
        bw, bh = x2 - x1, y2 - y1
        if bw < 20 or bh < 20:
            return False
        ar = bh / float(bw)
        if ar < 0.38 or ar > 1.85:
            return False

        crop = frame_bgr[max(0, y1):min(frame_bgr.shape[0], y2), max(0, x1):min(frame_bgr.shape[1], x2)]
        if crop.size == 0:
            return False
        ch, cw = crop.shape[:2]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

        # Upper canopy check (Yellow/Orange hood)
        canopy = hsv[:int(ch * 0.50), :]
        tot_canopy = canopy.shape[0] * canopy.shape[1]
        if tot_canopy == 0:
            return False
        yellow_canopy = ((canopy[:, :, 0] >= 12) & (canopy[:, :, 0] <= 42) & (canopy[:, :, 1] >= 35) & (canopy[:, :, 2] >= 45))
        yellow_ratio = np.sum(yellow_canopy) / tot_canopy

        # Lower body check (CNG Green or Dark body panels / open cabin)
        body = hsv[int(ch * 0.45):, :]
        tot_body = body.shape[0] * body.shape[1]
        if tot_body == 0:
            return False
        green_body = ((body[:, :, 0] >= 30) & (body[:, :, 0] <= 98) & (body[:, :, 1] >= 25))
        dark_body = (body[:, :, 2] < 80)
        green_dark_ratio = (np.sum(green_body) + np.sum(dark_body)) / tot_body

        # Stricter thresholds: Require at least 35% of the upper half to be yellow
        # and at least 35% of the lower half to be dark/green to avoid false positives on standard cars.
        return yellow_ratio >= 0.35 and green_dark_ratio >= 0.35

    def detect(self, frame_bgr):
        h, w = frame_bgr.shape[:2]
        results = self.model(
            frame_bgr,
            imgsz=640,
            conf=self.conf_thresh,
            iou=self.iou_thresh,
            device=self.device,
            verbose=False
        )[0]

        detections = []
        person_count = 0
        vehicle_count = 0
        has_threat = False
        threat_name = None

        raw_persons = []
        raw_vehicles = []
        raw_others = []

        for box in results.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            cls_name = results.names[cls_id].lower()
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            bw = x2 - x1
            bh = y2 - y1

            if bw < 18 or bh < 18:
                continue

            is_threat = cls_name in self.threat_classes or cls_id in [43, 76]
            if is_threat:
                has_threat = True
                threat_name = cls_name.upper()

            # Strict anatomical validation for PERSON to eliminate signs/poles/traffic lights
            if cls_id == 0:
                continue # Skip person detection completely as per user request

            elif cls_name in self.vehicle_classes:
                # Ignore far distance vehicles (small bounding boxes) to process efficiently
                if bw < 75 or bh < 60:
                    continue

                is_rickshaw = self.is_auto_rickshaw(frame_bgr, (x1, y1, x2, y2))
                if not is_rickshaw and conf < 0.35:
                    continue
                if is_rickshaw and conf < 0.16:
                    continue

                # Indian 3-Wheeler Auto-Rickshaw Re-Classification
                if is_rickshaw:
                    cls_name = "auto_rickshaw"
                    disp_label = "AUTO-RICKSHAW"
                    conf = max(conf, 0.85)
                else:
                    disp_label = cls_name.upper()

                raw_vehicles.append({
                    "box": (x1, y1, x2, y2),
                    "class_name": cls_name,
                    "label": disp_label,
                    "confidence": conf,
                    "is_threat": is_threat,
                    "is_vehicle": True,
                    "is_person": False
                })
            else:
                if conf < 0.35:
                    continue
                raw_others.append({
                    "box": (x1, y1, x2, y2),
                    "class_name": cls_name,
                    "label": cls_name.upper(),
                    "confidence": conf,
                    "is_threat": is_threat,
                    "is_vehicle": False,
                    "is_person": False
                })

        # Deduplicate vehicle bounding boxes with IoU > 0.50
        dedup_vehicles = []
        # Sort by bounding box area descending so the largest box always wins and suppresses smaller boxes inside it
        raw_vehicles.sort(key=lambda x: (x["box"][2] - x["box"][0]) * (x["box"][3] - x["box"][1]), reverse=True)
        for v in raw_vehicles:
            vx1, vy1, vx2, vy2 = v["box"]
            keep = True
            for dv in dedup_vehicles:
                dx1, dy1, dx2, dy2 = dv["box"]
                ix1, iy1 = max(vx1, dx1), max(vy1, dy1)
                ix2, iy2 = min(vx2, dx2), min(vy2, dy2)
                if ix2 > ix1 and iy2 > iy1:
                    inter = (ix2 - ix1) * (iy2 - iy1)
                    v_area = (vx2 - vx1)*(vy2 - vy1)
                    d_area = (dx2 - dx1)*(dy2 - dy1)
                    union = v_area + d_area - inter
                    
                    iou = inter / max(1.0, float(union))
                    containment = inter / max(1.0, float(min(v_area, d_area)))
                    
                    # Suppress if IoU is high OR if the smaller box is almost entirely inside the larger one
                    if iou > 0.45 or containment > 0.70:
                        keep = False
                        break
            if keep:
                dedup_vehicles.append(v)

        # Suppress persons that are actually artifacts on vehicle edges or inside vehicles (e.g. buses, trucks)
        valid_persons = []
        for p in raw_persons:
            px1, py1, px2, py2 = p["box"]
            p_area = (px2 - px1) * (py2 - py1)
            is_vehicle_artifact = False
            for v in dedup_vehicles:
                vx1, vy1, vx2, vy2 = v["box"]
                ix1, iy1 = max(px1, vx1), max(py1, vy1)
                ix2, iy2 = min(px2, vx2), min(py2, vy2)
                if ix2 > ix1 and iy2 > iy1:
                    inter_area = (ix2 - ix1) * (iy2 - iy1)
                    # If person box is >30% inside a bus/truck/car, it is a surface artifact on the vehicle
                    if inter_area / float(p_area) > 0.30:
                        is_vehicle_artifact = True
                        break
            if not is_vehicle_artifact:
                valid_persons.append(p)

        detections = valid_persons + dedup_vehicles + raw_others
        person_count = len(valid_persons)
        vehicle_count = len(dedup_vehicles)

        return {
            "detections": detections,
            "person_count": person_count,
            "vehicle_count": vehicle_count,
            "has_threat": has_threat,
            "threat_name": threat_name
        }
