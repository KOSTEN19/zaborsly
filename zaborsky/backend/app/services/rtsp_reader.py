import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from urllib.parse import unquote, urlparse, urlunparse

import cv2
import numpy as np
import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from app.config import settings
from app.database import SessionLocal
from app.models import Camera
from app.services.runtime_config import cfg

logger = logging.getLogger(__name__)

_FFMPEG_OPTS_SET = False


def pick_camera_source(http: str, rtsp: str, video_file: str) -> str:
    return (http or rtsp or video_file or "").strip()


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


def mask_stream_url(url: str) -> str:
    if not url or not url.startswith(("rtsp", "http")):
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


def _strip_credentials(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, host, parsed.path, parsed.params, parsed.query, parsed.fragment))


def _is_snapshot_url(url: str) -> bool:
    lower = url.lower()
    return "snapshot.cgi" in lower or lower.endswith(".jpg") or "snap.jpg" in lower


def _is_mjpeg_url(url: str) -> bool:
    lower = url.lower()
    return url.startswith("http") and (
        "mjpg" in lower or "video.cgi" in lower or "mjpeg" in lower or "axis-cgi/mjpg" in lower
    )


def _http_auth(user: str | None, password: str) -> HTTPDigestAuth | HTTPBasicAuth | None:
    if not user:
        return None
    return HTTPDigestAuth(user, password)


class _HttpMjpegReader:
    """Dahua/Hikvision MJPEG over HTTP with digest auth."""

    def __init__(self, source: str):
        self.source = source
        self._session = requests.Session()
        self._auth_user, self._auth_pass = _parse_credentials(source)
        self._stream_url = _strip_credentials(source)
        self._resp: requests.Response | None = None
        self._buffer = b""
        self.last_error: str | None = None

    def _connect(self) -> bool:
        self.close_stream()
        auth = _http_auth(self._auth_user, self._auth_pass)
        try:
            resp = self._session.get(self._stream_url, auth=auth, stream=True, timeout=15)
            if resp.status_code == 401 and self._auth_user:
                resp = self._session.get(
                    self._stream_url,
                    auth=HTTPBasicAuth(self._auth_user, self._auth_pass),
                    stream=True,
                    timeout=15,
                )
            resp.raise_for_status()
            self._resp = resp
            self._buffer = b""
            self.last_error = None
            return True
        except requests.RequestException as exc:
            self.last_error = str(exc)
            return False

    def read_frame(self) -> np.ndarray | None:
        if self._resp is None and not self._connect():
            return None

        assert self._resp is not None
        try:
            for _ in range(80):
                chunk = next(self._resp.iter_content(chunk_size=8192), b"")
                if not chunk:
                    if not self._connect():
                        return None
                    continue
                self._buffer += chunk
                start = self._buffer.find(b"\xff\xd8")
                end = self._buffer.find(b"\xff\xd9")
                if start == -1 or end == -1 or end <= start:
                    if len(self._buffer) > 4_000_000:
                        self._buffer = self._buffer[-512_000:]
                    continue
                jpg = self._buffer[start : end + 2]
                self._buffer = self._buffer[end + 2 :]
                frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    return frame
            self.last_error = "mjpeg frame not found in stream"
            return None
        except requests.RequestException as exc:
            self.last_error = str(exc)
            self.close_stream()
            return None

    def close_stream(self):
        if self._resp is not None:
            self._resp.close()
            self._resp = None
        self._buffer = b""

    def close(self):
        self.close_stream()
        self._session.close()


@dataclass
class FrameSource:
    camera_id: int
    source: str
    roi: str | None = None


class RTSPReader:
    """Reads frames from RTSP, HTTP MJPEG or HTTP snapshot URL."""

    def __init__(self, camera_id: int, source: str):
        self.camera_id = camera_id
        self.source = source
        self._cap: cv2.VideoCapture | None = None
        self._session: requests.Session | None = None
        self._mjpeg: _HttpMjpegReader | None = None
        self._snapshot_url: str | None = None
        self._snapshot_auth: HTTPBasicAuth | HTTPDigestAuth | None = None
        self._auth_user: str | None = None
        self._auth_pass: str = ""
        self._last_read_time = 0.0
        self.is_online = False
        self.last_error: str | None = None

        if _is_mjpeg_url(source):
            self._mjpeg = _HttpMjpegReader(source)
        elif _is_snapshot_url(source):
            self._auth_user, self._auth_pass = _parse_credentials(source)
            if self._auth_user:
                self._snapshot_auth = HTTPDigestAuth(self._auth_user, self._auth_pass)
            self._snapshot_url = _strip_credentials(source)
            self._session = requests.Session()

    def _open_stream(self) -> bool:
        if self._mjpeg or self._snapshot_url:
            return True

        if self.source.startswith("rtsp"):
            _ensure_ffmpeg_rtsp_options()

        if self._cap is not None:
            self._cap.release()
            self._cap = None

        self._cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        if self.source.startswith(("rtsp", "http")):
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if self._cap.isOpened():
            self.last_error = None
            return True

        self.last_error = "cannot open stream"
        return False

    def _read_snapshot(self) -> np.ndarray | None:
        assert self._snapshot_url and self._session
        try:
            resp = self._session.get(self._snapshot_url, auth=self._snapshot_auth, timeout=10)
            if resp.status_code == 401 and self._auth_user:
                resp = self._session.get(
                    self._snapshot_url,
                    auth=HTTPBasicAuth(self._auth_user, self._auth_pass),
                    timeout=10,
                )
            resp.raise_for_status()
            frame = cv2.imdecode(np.frombuffer(resp.content, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                self.last_error = "snapshot decode failed"
                return None
            return frame
        except requests.RequestException as exc:
            self.last_error = str(exc)
            return None

    def read_raw(self) -> np.ndarray | None:
        """Read frame at live preview rate, full resolution (before ANPR resize)."""
        interval = cfg.live_preview_interval_ms / 1000.0
        now = time.time()
        if now - self._last_read_time < interval:
            return None

        frame: np.ndarray | None = None

        if self._mjpeg:
            frame = self._mjpeg.read_frame()
            if frame is None:
                self.last_error = self._mjpeg.last_error or "mjpeg read failed"
        elif self._snapshot_url:
            frame = self._read_snapshot()
        else:
            if self._cap is None or not self._cap.isOpened():
                if not self._open_stream():
                    self.is_online = False
                    logger.warning(
                        "Camera %s: cannot open %s (%s)",
                        self.camera_id,
                        mask_stream_url(self.source),
                        self.last_error,
                    )
                    time.sleep(2)
                    return None

            ret, frame = self._cap.read()
            if not ret or frame is None:
                self.is_online = False
                self.last_error = "frame read failed"
                logger.warning(
                    "Camera %s: frame read failed, reconnecting to %s",
                    self.camera_id,
                    mask_stream_url(self.source),
                )
                self._open_stream()
                time.sleep(1)
                return None

        if frame is None:
            self.is_online = False
            logger.warning(
                "Camera %s: read failed (%s) %s",
                self.camera_id,
                self.last_error,
                mask_stream_url(self.source),
            )
            time.sleep(2)
            return None

        self._last_read_time = now
        self.is_online = True
        self.last_error = None
        return frame

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self._mjpeg is not None:
            self._mjpeg.close()
            self._mjpeg = None
        if self._session is not None:
            self._session.close()
            self._session = None


mask_rtsp_url = mask_stream_url


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
        (
            1,
            pick_camera_source(cfg.camera_1_http, cfg.camera_1_rtsp, settings.video_file_1),
            cfg.camera_1_roi,
        ),
        (
            2,
            pick_camera_source(cfg.camera_2_http, cfg.camera_2_rtsp, settings.video_file_2),
            cfg.camera_2_roi,
        ),
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
