"""Yüz crop kalitesi: bulanıklık (Laplacian) ve minimum genişlik."""

from __future__ import annotations

import numpy as np

BLUR_ESIK = 100.0
MIN_GENISLIK = 80.0


def bulaniklik(crop) -> float:
    """Laplacian varyansı; düşük değer bulanık demektir."""
    if crop is None:
        return 0.0
    img = np.asarray(crop)
    if img.size == 0:
        return 0.0
    try:
        import cv2
    except Exception:
        return 0.0
    if img.ndim == 3:
        gri = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gri = img
    if gri.dtype != np.uint8:
        gri = np.clip(gri, 0, 255).astype(np.uint8)
    return float(cv2.Laplacian(np.ascontiguousarray(gri), cv2.CV_64F).var())


def kaydedilebilir(crop, bbox=None) -> bool:
    """80px'den dar veya bulanık yüz diske/DB'ye yazılmaz."""
    if bbox is not None and len(bbox) >= 4:
        gen = float(bbox[2]) - float(bbox[0])
        if gen < MIN_GENISLIK:
            return False
    elif crop is not None:
        img = np.asarray(crop)
        if img.ndim >= 2 and img.shape[1] < MIN_GENISLIK:
            return False
    return bulaniklik(crop) >= BLUR_ESIK
