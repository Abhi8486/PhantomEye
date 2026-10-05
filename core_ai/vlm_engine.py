"""
Microsoft Florence-2 Vision-Language Foundation Model Engine
Provides Dense Region Grounding, Detailed Forensic Captions, and Complex Scene Intelligence.
"""

import torch
import cv2
from PIL import Image
from transformers import AutoModelForCausalLM, AutoProcessor


class Florence2VLM:
    def __init__(self, model_id="microsoft/Florence-2-base"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32
        print(f"[*] Initializing Florence-2 VLM on {self.device.upper()}...")
        self.model = AutoModelForCausalLM.from_pretrained(model_id, torch_dtype=self.dtype, trust_remote_code=True).to(self.device)
        self.processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        print(f"[OK] Florence-2 VLM Ready on {self.device.upper()}!")

    def generate_caption(self, frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        w, h = pil_img.size

        task = "<MORE_DETAILED_CAPTION>"
        inputs = self.processor(text=task, images=pil_img, return_tensors="pt").to(self.device)
        if self.device == "cuda":
            inputs = {k: v.to(dtype=self.dtype) if v.dtype == torch.float32 else v for k, v in inputs.items()}

        with torch.no_grad():
            out = self.model.generate(input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"], max_new_tokens=256)
        
        gen_text = self.processor.batch_decode(out, skip_special_tokens=False)[0]
        res = self.processor.post_process_generation(gen_text, task=task, image_size=(w, h))
        return res.get(task, "No caption generated.")

    def dense_grounding(self, frame_bgr):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        w, h = pil_img.size

        task = "<DENSE_REGION_CAPTION>"
        inputs = self.processor(text=task, images=pil_img, return_tensors="pt").to(self.device)
        if self.device == "cuda":
            inputs = {k: v.to(dtype=self.dtype) if v.dtype == torch.float32 else v for k, v in inputs.items()}

        with torch.no_grad():
            out = self.model.generate(input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"], max_new_tokens=512)

        gen_text = self.processor.batch_decode(out, skip_special_tokens=False)[0]
        res = self.processor.post_process_generation(gen_text, task=task, image_size=(w, h))
        dense = res.get(task, {})
        return [{"box": tuple(map(int, b)), "label": l} for b, l in zip(dense.get("bboxes", []), dense.get("labels", []))]
