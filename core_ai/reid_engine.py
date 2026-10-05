"""
Multi-Channel Person & Face Re-Identification Engine
Extracts 512-dimensional feature embeddings for cross-camera suspect tracking.
"""

import cv2
import numpy as np
import torch


class PersonReIDEngine:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[*] Initializing Multi-Channel Re-ID Embedder on {self.device.upper()}...")
        # Gallery of known suspects
        self.gallery = {}

    def extract_embedding(self, crop_bgr):
        """
        Extracts normalized multi-channel color + spatial gradient biometric vector (512-d).
        """
        if crop_bgr is None or crop_bgr.size == 0:
            return np.zeros(512, dtype=np.float32)

        resized = cv2.resize(crop_bgr, (128, 256))
        # Color histograms in HSV + LAB
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(resized, cv2.COLOR_BGR2LAB)
        
        hist_h = cv2.calcHist([hsv], [0], None, [64], [0, 180])
        hist_s = cv2.calcHist([hsv], [1], None, [64], [0, 256])
        hist_v = cv2.calcHist([hsv], [2], None, [64], [0, 256])
        hist_l = cv2.calcHist([lab], [0], None, [64], [0, 256])
        hist_a = cv2.calcHist([lab], [1], None, [64], [0, 256])
        hist_b = cv2.calcHist([lab], [2], None, [64], [0, 256])
        
        # Spatial gradients
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        sobelx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        hist_gx = cv2.calcHist([sobelx], [0], None, [64], [-255, 255])
        hist_gy = cv2.calcHist([sobely], [0], None, [64], [-255, 255])

        vec = np.concatenate([hist_h, hist_s, hist_v, hist_l, hist_a, hist_b, hist_gx, hist_gy]).flatten()
        norm = np.linalg.norm(vec)
        return vec / (norm + 1e-7)

    def compare(self, emb1, emb2):
        """Cosine similarity metric."""
        return float(np.dot(emb1, emb2))
