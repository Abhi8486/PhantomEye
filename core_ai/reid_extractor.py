"""
Deep Neural Network Re-ID & Visual Embedding Extractor
Uses MobileNetV3-Small / PyTorch on CUDA for real learned visual embeddings.
Replaces naive color histograms with a true deep convolutional metric space (576-d L2-normalized).
"""

import cv2
import torch
import torch.nn as nn
import torchvision.transforms as T
import torchvision.models as models
import numpy as np
from typing import Optional, Union


class DeepReIDExtractor:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(DeepReIDExtractor, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, device: Optional[str] = None):
        if getattr(self, "_initialized", False):
            return

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[*] Initializing Deep Re-ID Extractor on {self.device.upper()}...")

        # Load MobileNetV3 backbone pre-trained on ImageNet
        weights = models.MobileNet_V3_Small_Weights.DEFAULT
        backbone = models.mobilenet_v3_small(weights=weights)
        
        # Remove final classifier to extract feature representation
        self.feature_extractor = nn.Sequential(
            backbone.features,
            backbone.avgpool,
            nn.Flatten()
        ).to(self.device).eval()

        # Image preprocessing pipeline for Re-ID crops (224x224, ImageNet normalization)
        self.transform = T.Compose([
            T.ToPILImage(),
            T.Resize((224, 224)),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

        self._initialized = True
        print(f"[OK] Deep Re-ID Extractor Ready on {self.device.upper()} (Embedding Dim: 576)")

    @torch.no_grad()
    def extract_embedding(self, crop_bgr: np.ndarray) -> np.ndarray:
        """
        Extracts an L2-normalized 576-dimensional visual embedding vector from a BGR crop.
        """
        if crop_bgr is None or crop_bgr.size == 0 or crop_bgr.shape[0] < 10 or crop_bgr.shape[1] < 10:
            # Fallback for empty crop: zero vector
            return np.zeros(576, dtype=np.float32)

        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        tensor = self.transform(rgb).unsqueeze(0).to(self.device)
        
        features = self.feature_extractor(tensor).cpu().squeeze(0).numpy()
        
        # L2-normalization for cosine distance computation
        norm = np.linalg.norm(features)
        if norm > 1e-6:
            features = features / norm
        else:
            features = np.zeros(576, dtype=np.float32)

        return features

    @classmethod
    def compute_cosine_similarity(cls, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Computes cosine similarity between two L2-normalized visual embeddings.
        Returns float in range [0.0, 1.0].
        """
        if emb1 is None or emb2 is None:
            return 0.0
        n1 = np.linalg.norm(emb1)
        n2 = np.linalg.norm(emb2)
        if n1 < 1e-6 or n2 < 1e-6:
            return 0.0
        dot = float(np.dot(emb1, emb2) / (n1 * n2))
        # Map [-1, 1] to [0, 1]
        return max(0.0, min(1.0, (dot + 1.0) / 2.0))


# Global singleton instance
reid_extractor = DeepReIDExtractor()
