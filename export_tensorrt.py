import os
import torch
from ultralytics import YOLO

def export_model():
    print("==================================================")
    print("🚀 YOLOv8 TensorRT Export Utility for 10GB GPUs")
    print("==================================================")
    
    if not torch.cuda.is_available():
        print("❌ ERROR: CUDA GPU not detected! You must run this in an environment with an NVIDIA GPU (like Colab).")
        return
        
    model_name = "yolov8m.pt"
    engine_name = "yolov8m.engine"
    
    print(f"[*] Downloading and loading {model_name}...")
    model = YOLO(model_name)
    
    print(f"[*] Exporting {model_name} to TensorRT {engine_name}...")
    print("[!] This process will take 2-5 minutes and might consume a lot of RAM. Please wait...")
    
    # Export to TensorRT, using half-precision (FP16) which is perfectly safe and 2x faster on RTX cards
    # Workspace=4 allocates 4GB of VRAM for the conversion process
    success = model.export(
        format="engine",
        half=True, 
        workspace=4, 
        device=0,
        imgsz=640
    )
    
    if success:
        print("==================================================")
        print(f"✅ SUCCESS! TensorRT Engine created.")
        print("The backend will automatically detect and load 'yolov8m.engine' on the next restart!")
        print("==================================================")
    else:
        print("❌ ERROR: Failed to export the model.")

if __name__ == "__main__":
    export_model()
