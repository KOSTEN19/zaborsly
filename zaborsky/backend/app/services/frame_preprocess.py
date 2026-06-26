import cv2
import numpy as np

from app.config import settings


def resize_frame(frame: np.ndarray, max_width: int) -> np.ndarray:
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / w
    return cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def apply_roi(frame: np.ndarray, roi: str | None) -> np.ndarray:
    """ROI format: x,y,w,h as fractions 0-1 or pixels if values > 1."""
    if not roi:
        return frame
    try:
        parts = [float(p.strip()) for p in roi.split(",")]
        if len(parts) != 4:
            return frame
        h, w = frame.shape[:2]
        x, y, rw, rh = parts
        if all(0 < v <= 1 for v in parts):
            x1, y1 = int(x * w), int(y * h)
            x2, y2 = int((x + rw) * w), int((y + rh) * h)
        else:
            x1, y1, x2, y2 = int(x), int(y), int(x + rw), int(y + rh)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return frame
        return frame[y1:y2, x1:x2]
    except (ValueError, TypeError):
        return frame


def enhance_for_anpr(frame: np.ndarray) -> np.ndarray:
    """Improve contrast for OCR without heavy compute."""
    if not settings.enable_clahe:
        return frame

    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l_channel, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)
    enhanced = cv2.merge([l_channel, a, b])
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)


def prepare_anpr_frame(frame: np.ndarray, roi: str | None = None) -> np.ndarray:
    cropped = apply_roi(frame, roi)
    resized = resize_frame(cropped, settings.anpr_max_frame_width)
    return enhance_for_anpr(resized)


def prepare_live_frame(frame: np.ndarray) -> np.ndarray:
    return resize_frame(frame, settings.live_max_frame_width)
