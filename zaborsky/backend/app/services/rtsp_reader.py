import logging
import os
import time
import uuid
from dataclasses import dataclass

import cv2
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class FrameSource:
    camera_id: int
    source: str
    roi: str | None = None


class RTSPReader:
    def __init__(self, camera_id: int, source: str):
        self.camera_id = camera_id
        self.source = source
        self._cap: cv2.VideoCapture | None = None
        self._last_read_time = 0.0
        self.is_online = False

    def _open(self) -> bool:
        if self._cap is not None:
            self._cap.release()
        self._cap = cv2.VideoCapture(self.source)
        if self.source.startswith("rtsp"):
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return self._cap.isOpened()

    def read_raw(self) -> np.ndarray | None:
        """Read frame at live preview rate, full resolution (before ANPR resize)."""
        interval = settings.live_preview_interval_ms / 1000.0
        now = time.time()
        if now - self._last_read_time < interval:
            return None

        if self._cap is None or not self._cap.isOpened():
            if not self._open():
                logger.warning("Camera %s: cannot open source %s", self.camera_id, self.source)
                self.is_online = False
                time.sleep(2)
                return None

        ret, frame = self._cap.read()
        if not ret or frame is None:
            logger.warning("Camera %s: frame read failed, reconnecting", self.camera_id)
            self.is_online = False
            self._open()
            time.sleep(1)
            return None

        self._last_read_time = now
        self.is_online = True
        return frame

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None


def save_frame(frame: np.ndarray, subdir: str = "detections") -> str:
    os.makedirs(os.path.join(settings.photo_dir, subdir), exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    rel_path = os.path.join(subdir, filename)
    abs_path = os.path.join(settings.photo_dir, rel_path)
    cv2.imwrite(abs_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return rel_path


def get_camera_sources() -> list[FrameSource]:
    sources: list[FrameSource] = []
    pairs = [
        (1, settings.camera_1_rtsp or settings.video_file_1, settings.camera_1_roi),
        (2, settings.camera_2_rtsp or settings.video_file_2, settings.camera_2_roi),
    ]
    for camera_id, source, roi in pairs:
        if source:
            sources.append(FrameSource(camera_id=camera_id, source=source, roi=roi or None))
    return sources
