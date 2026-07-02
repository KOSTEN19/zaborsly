import logging
import os
import re
import time
import uuid
import urllib.request
from dataclasses import dataclass
from urllib.parse import unquote, urlparse, urlunparse

import cv2
import numpy as np

from app.config import settings
from app.database import SessionLocal
from app.models import Camera
from app.services.runtime_config import cfg, get_dict

logger = logging.getLogger(__name__)

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def pick_camera_source(http: str, video_file: str) -> str:
    return (http or video_file or "").strip()


def mask_stream_url(url: str) -> str:
    if not url or not url.startswith("http"):
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


def _parse_credentials(url: str) -> tuple[str | None, str]:
    parsed = urlparse(url)
    if not parsed.username:
        return None, ""
    return unquote(parsed.username), unquote(parsed.password or "")


def _snapshot_url(url: str) -> str:
    if "snapshot.cgi" in url.lower():
        return url
    return url.replace("/cgi-bin/mjpg/video.cgi", "/cgi-bin/snapshot.cgi").replace(
        "mjpg/video.cgi", "snapshot.cgi"
    )


def _decode_jpeg(data: bytes) -> np.ndarray | None:
    if not data:
        return None
    return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)


def _urllib_opener(url: str) -> urllib.request.OpenerDirector:
    parsed = urlparse(url)
    user, password = _parse_credentials(url)
    host = parsed.hostname or ""
    port = parsed.port or 80
    base = f"{parsed.scheme}://{host}:{port}/"

    mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    if user:
        mgr.add_password(None, base, user, password)
        mgr.add_password(None, f"{parsed.scheme}://{host}/", user, password)

    handlers = [
        urllib.request.HTTPDigestAuthHandler(mgr),
        urllib.request.HTTPBasicAuthHandler(mgr),
    ]
    return urllib.request.build_opener(*handlers)


def _urllib_fetch_jpeg(url: str, timeout: int = 15) -> np.ndarray | None:
    headers = {"User-Agent": BROWSER_UA}

    # 1) Как браузер: логин/пароль прямо в URL
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            frame = _decode_jpeg(resp.read())
            if frame is not None:
                return frame
    except Exception as exc:
        logger.debug("urllib plain %s: %s", mask_stream_url(url), exc)

    # 2) Digest/Basic auth (если камера требует challenge)
    try:
        opener = _urllib_opener(url)
        req = urllib.request.Request(url, headers=headers)
        with opener.open(req, timeout=timeout) as resp:
            return _decode_jpeg(resp.read())
    except Exception as exc:
        logger.debug("urllib auth %s: %s", mask_stream_url(url), exc)
        return None


@dataclass
class FrameSource:
    camera_id: int
    source: str
    roi: str | None = None


class _HttpStream:
    """
    Читает HTTP-камеру так же, как браузер:
    1) OpenCV/ffmpeg по полному URL (MJPEG)
    2) urllib snapshot (один кадр, digest auth как в браузере)
    """

    def __init__(self, source: str):
        self.source = source.strip()
        self._snapshot = _snapshot_url(self.source)
        self._cap: cv2.VideoCapture | None = None
        self._mode = "auto"
        self._failures = 0
        self.last_error: str | None = None
        logger.info("HTTP camera init: %s", mask_stream_url(self.source))

    def _open_opencv(self) -> bool:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

        os.environ.setdefault(
            "OPENCV_FFMPEG_CAPTURE_OPTIONS",
            f"user_agent;{BROWSER_UA}|stimeout;15000000",
        )
        cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if cap.isOpened():
            self._cap = cap
            self._mode = "opencv"
            self.last_error = None
            logger.info("HTTP camera: OpenCV/ffmpeg connected")
            return True

        cap.release()
        self.last_error = "opencv cannot open stream"
        return False

    def _read_opencv(self) -> np.ndarray | None:
        if self._cap is None or not self._cap.isOpened():
            if not self._open_opencv():
                return None
        assert self._cap is not None
        ok, frame = self._cap.read()
        if ok and frame is not None:
            return frame
        self.last_error = "opencv frame read failed"
        self._open_opencv()
        return None

    def _read_snapshot(self) -> np.ndarray | None:
        for url in (self._snapshot, self.source):
            frame = _urllib_fetch_jpeg(url)
            if frame is not None:
                self.last_error = None
                return frame
        self.last_error = "snapshot fetch failed"
        return None

    def read_frame(self) -> np.ndarray | None:
        # Snapshot через urllib (digest как в браузере) — самый надёжный способ
        frame = self._read_snapshot()
        if frame is not None:
            self._failures = 0
            return frame

        # MJPEG поток через ffmpeg/OpenCV — как вкладка в браузере
        if self._mode != "snapshot_only":
            frame = self._read_opencv()
            if frame is not None:
                self._failures = 0
                return frame

        self._failures += 1
        if self._failures >= 5 and self._mode != "snapshot_only":
            logger.warning("HTTP camera: OpenCV failed, only snapshot mode")
            self._mode = "snapshot_only"
            if self._cap:
                self._cap.release()
                self._cap = None

        return None

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None


mask_rtsp_url = mask_stream_url


class CameraReader:
    """Читает кадры с HTTP-камеры или локального видеофайла."""

    def __init__(self, camera_id: int, source: str):
        self.camera_id = camera_id
        self.source = source
        self._http: _HttpStream | None = None
        self._cap: cv2.VideoCapture | None = None
        self._last_read_time = 0.0
        self.is_online = False
        self.last_error: str | None = None

        if source.startswith("http"):
            self._http = _HttpStream(source)
        else:
            self._cap = cv2.VideoCapture(source)

    def read_raw(self) -> np.ndarray | None:
        interval = cfg.live_preview_interval_ms / 1000.0
        now = time.time()
        if now - self._last_read_time < interval:
            return None

        frame: np.ndarray | None = None

        if self._http:
            frame = self._http.read_frame()
            if frame is None:
                self.last_error = self._http.last_error or "http read failed"
        elif self._cap is not None:
            if not self._cap.isOpened():
                self._cap = cv2.VideoCapture(self.source)
            ret, frame = self._cap.read()
            if not ret or frame is None:
                self.last_error = "video file read failed"
                frame = None

        if frame is None:
            self.is_online = False
            logger.warning(
                "Camera %s offline: %s — %s",
                self.camera_id,
                mask_stream_url(self.source),
                self.last_error or "unknown",
            )
            time.sleep(0.5)
            return None

        self._last_read_time = now
        self.is_online = True
        self.last_error = None
        return frame

    def close(self):
        if self._http:
            self._http.close()
            self._http = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None


RTSPReader = CameraReader


def save_frame(frame: np.ndarray, subdir: str = "detections") -> str:
    os.makedirs(os.path.join(settings.photo_dir, subdir), exist_ok=True)
    filename = f"{uuid.uuid4().hex}.jpg"
    rel_path = os.path.join(subdir, filename)
    abs_path = os.path.join(settings.photo_dir, rel_path)
    cv2.imwrite(abs_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return rel_path


def _cfg_http_url(camera_num: int) -> str:
    d = get_dict()
    http = (d.get(f"camera_{camera_num}_http") or "").strip()
    if http:
        return http
    legacy = (d.get(f"camera_{camera_num}_rtsp") or "").strip()
    if legacy.startswith("http"):
        return legacy
    return ""


def get_camera_sources() -> list[FrameSource]:
    sources: list[FrameSource] = []
    pairs = [
        (1, pick_camera_source(_cfg_http_url(1), settings.video_file_1), cfg.camera_1_roi),
        (2, pick_camera_source(_cfg_http_url(2), settings.video_file_2), cfg.camera_2_roi),
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


def get_camera_source(camera_id: int) -> FrameSource | None:
    for src in get_camera_sources():
        if src.camera_id == camera_id:
            return src
    return None
