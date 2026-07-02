import time

import cv2
import numpy as np

from app.services.runtime_config import cfg


class MotionDetector:
    """Cheap motion gate — skip ANPR when scene is static."""

    def __init__(self):
        self._prev_gray: np.ndarray | None = None
        self._last_motion_at = 0.0
        self._last_anpr_at = 0.0

    def is_scene_active(self) -> bool:
        return (time.time() - self._last_motion_at) <= cfg.motion_tail_sec

    def _to_small_gray(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, (320, 180), interpolation=cv2.INTER_AREA)

    def has_motion(self, frame: np.ndarray) -> bool:
        small = self._to_small_gray(frame)
        if self._prev_gray is None:
            self._prev_gray = small
            return True

        diff = cv2.absdiff(self._prev_gray, small)
        self._prev_gray = small

        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        motion_ratio = np.count_nonzero(thresh) / thresh.size
        return motion_ratio >= cfg.motion_min_area_ratio

    def should_run_anpr(self, frame: np.ndarray) -> bool:
        now = time.time()
        motion = self.has_motion(frame)

        if motion:
            self._last_motion_at = now

        within_tail = (now - self._last_motion_at) <= cfg.motion_tail_sec
        if not motion and not within_tail:
            return False

        min_gap = cfg.anpr_min_interval_ms / 1000.0
        if now - self._last_anpr_at < min_gap:
            return False

        self._last_anpr_at = now
        return True
