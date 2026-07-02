import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

import cv2
import numpy as np

from app.config import settings
from app.database import SessionLocal
from app.models import Camera
from app.services.runtime_config import cfg

logger = logging.getLogger(__name__)

_FFMPEG_OPTS_SET = False


def _ensure_ffmpeg_rtsp_options():
    global _FFMPEG_OPTS_SET
    if _FFMPEG_OPTS_SET:
        return
    if cfg.rtsp_use_tcp:
        timeout_us = max(cfg.rtsp_open_timeout_sec, 1) * 1_000_000
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            f"rtsp_transport;tcp|stimeout;{timeout_us}|max_delay;500000"
        )
        logger.info("RTSP: using ffmpeg transport=tcp (timeout %ss)", cfg.rtsp_open_timeout_sec)
    _FFMPEG_OPTS_SET = True


def mask_rtsp_url(url: str) -> str:
    if not url or not url.startswith("rtsp"):
        return url
    try:
        parsed = urlparse(url)
        if not parsed.password:
            return url
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        user = parsed.username or ""
        netloc = f"{user}:***@{host}" if user else host
        return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    except Exception:
        return re.sub(r":([^:@/]+)@", ":***@", url, count=1)


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
        self.last_error: str | None = None

    def _open(self) -> bool:
        _ensure_ffmpeg_rtsp_options()
        if self._cap is not None:
            self._cap.release()
            self._cap = None

        self._cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        if self.source.startswith("rtsp"):
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if self._cap.isOpened():
            self.last_error = None
            return True

        self.last_error = "cannot open stream"
        return False

    def read_raw(self) -> np.ndarray | None:
        """Read frame at live preview rate, full resolution (before ANPR resize)."""
        interval = cfg.live_preview_interval_ms / 1000.0
        now = time.time()
        if now - self._last_read_time < interval:
            return None

        if self._cap is None or not self._cap.isOpened():
            if not self._open():
                self.is_online = False
                logger.warning(
                    "Camera %s: cannot open %s (%s)",
                    self.camera_id,
                    mask_rtsp_url(self.source),
                    self.last_error,
                )
                time.sleep(2)
                return None

        ret, frame = self._cap.read()
        if not ret or frame is None:
            self.is_online = False
            self.last_error = "frame read failed"
            logger.warning(
                "Camera %s: frame read failed (%s), reconnecting to %s",
                self.camera_id,
                self.last_error,
                mask_rtsp_url(self.source),
            )
            self._open()
            time.sleep(1)
            return None

        self._last_read_time = now
        self.is_online = True
        self.last_error = None
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
        (1, cfg.camera_1_rtsp or settings.video_file_1, cfg.camera_1_roi),
        (2, cfg.camera_2_rtsp or settings.video_file_2, cfg.camera_2_roi),
    ]
    db = SessionLocal()
    try:
        for position, source, roi in pairs:
            if not source:
                continue
            cam = db.query(Camera).filter(Camera.position == position).first()
            camera_id = cam.id if cam else position
            sources.append(FrameSource(camera_id=camera_id, source=source, roi=roi or None))
    finally:
        db.close()
    return sources
