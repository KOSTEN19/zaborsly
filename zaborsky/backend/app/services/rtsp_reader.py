import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse

import cv2
import numpy as np
import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

from app.config import settings
from app.database import SessionLocal
from app.models import Camera
from app.services.runtime_config import cfg, get_dict

logger = logging.getLogger(__name__)

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ZaborskyANPR/1.0)",
    "Connection": "keep-alive",
}


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


def _strip_credentials(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, host, parsed.path, parsed.params, parsed.query, parsed.fragment))


def _with_subtype(url: str, subtype: int) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs["subtype"] = [str(subtype)]
    if "channel" not in qs:
        qs["channel"] = ["1"]
    query = urlencode({k: v[0] for k, v in qs.items()})
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))


def _to_snapshot_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.replace("/cgi-bin/mjpg/video.cgi", "/cgi-bin/snapshot.cgi")
    if path == parsed.path:
        path = "/cgi-bin/snapshot.cgi"
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, parsed.fragment))


def _decode_jpeg(data: bytes) -> np.ndarray | None:
    if not data:
        return None
    frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    return frame


def _extract_jpeg(buffer: bytes) -> tuple[np.ndarray | None, bytes]:
    start = buffer.find(b"\xff\xd8")
    end = buffer.find(b"\xff\xd9")
    if start == -1 or end == -1 or end <= start:
        if len(buffer) > 2_000_000:
            return None, buffer[-256_000:]
        return None, buffer
    jpg = buffer[start : end + 2]
    rest = buffer[end + 2 :]
    return _decode_jpeg(jpg), rest


@dataclass
class FrameSource:
    camera_id: int
    source: str
    roi: str | None = None


class _DahuaHttpReader:
    """HTTP MJPEG / snapshot для Dahua (digest + basic, несколько URL)."""

    def __init__(self, source: str):
        self.source = source
        self._user, self._password = _parse_credentials(source)
        self._session = requests.Session()
        self._session.headers.update(HTTP_HEADERS)
        self._urls = self._build_url_candidates(source)
        self._url_index = 0
        self._mode = "mjpeg"
        self._resp: requests.Response | None = None
        self._chunk_iter = None
        self._buffer = b""
        self._failures = 0
        self.last_error: str | None = None

    def _build_url_candidates(self, source: str) -> list[str]:
        urls: list[str] = []
        for u in (source, _with_subtype(source, 1), _with_subtype(source, 0)):
            if u not in urls:
                urls.append(u)
        snap = _to_snapshot_url(source)
        if snap not in urls:
            urls.append(snap)
        return urls

    def _current_url(self) -> str:
        return self._urls[self._url_index % len(self._urls)]

    def _is_snapshot_url(self, url: str) -> bool:
        return "snapshot.cgi" in url.lower()

    def _request(self, url: str, *, stream: bool) -> requests.Response:
        stripped = _strip_credentials(url)
        auth_user, auth_pass = _parse_credentials(url)
        if not auth_user and self._user:
            auth_user, auth_pass = self._user, self._password

        attempts: list[tuple[str, dict]] = [
            ("full_url", {"url": url, "auth": None}),
            ("digest", {"url": stripped, "auth": HTTPDigestAuth(auth_user, auth_pass) if auth_user else None}),
            ("basic", {"url": stripped, "auth": HTTPBasicAuth(auth_user, auth_pass) if auth_user else None}),
            ("full_digest", {"url": url, "auth": HTTPDigestAuth(auth_user, auth_pass) if auth_user else None}),
        ]
        last_exc: Exception | None = None
        for name, kw in attempts:
            if kw["auth"] is None and name != "full_url":
                continue
            try:
                resp = self._session.get(
                    kw["url"],
                    auth=kw["auth"],
                    stream=stream,
                    timeout=(10, 30),
                    allow_redirects=True,
                )
                if resp.status_code == 401:
                    continue
                resp.raise_for_status()
                logger.debug("HTTP camera connected via %s: %s", name, mask_stream_url(kw["url"]))
                return resp
            except requests.RequestException as exc:
                last_exc = exc
                continue
        raise last_exc or requests.RequestException("all auth methods failed")

    def _connect_mjpeg(self) -> bool:
        self.close_stream()
        url = self._current_url()
        if self._is_snapshot_url(url):
            self._mode = "snapshot"
            return True
        try:
            self._resp = self._request(url, stream=True)
            ct = self._resp.headers.get("Content-Type", "")
            if "image/jpeg" in ct and "multipart" not in ct:
                self._mode = "snapshot"
            else:
                self._mode = "mjpeg"
            self._buffer = b""
            self._chunk_iter = self._resp.iter_content(chunk_size=16384)
            self.last_error = None
            return True
        except requests.RequestException as exc:
            self.last_error = str(exc)
            return False

    def _rotate_url(self):
        self._url_index += 1
        self._failures = 0
        url = self._current_url()
        self._mode = "snapshot" if self._is_snapshot_url(url) else "mjpeg"
        logger.info("HTTP camera: trying URL %s", mask_stream_url(url))

    def _read_snapshot_once(self) -> np.ndarray | None:
        url = self._current_url()
        try:
            resp = self._request(url, stream=False)
            frame = _decode_jpeg(resp.content)
            if frame is None:
                self.last_error = "snapshot decode failed"
            return frame
        except requests.RequestException as exc:
            self.last_error = str(exc)
            return None

    def _read_mjpeg_frame(self) -> np.ndarray | None:
        if self._resp is None or self._chunk_iter is None:
            if not self._connect_mjpeg():
                return None

        for _ in range(120):
            try:
                chunk = next(self._chunk_iter)
            except StopIteration:
                chunk = b""
            except requests.RequestException as exc:
                self.last_error = str(exc)
                self.close_stream()
                return None

            if not chunk:
                if not self._connect_mjpeg():
                    return None
                continue

            self._buffer += chunk
            frame, self._buffer = _extract_jpeg(self._buffer)
            if frame is not None:
                return frame

        self.last_error = "mjpeg: no jpeg frame in stream"
        return None

    def read_frame(self) -> np.ndarray | None:
        if self._mode == "snapshot" or self._is_snapshot_url(self._current_url()):
            frame = self._read_snapshot_once()
        else:
            frame = self._read_mjpeg_frame()

        if frame is not None:
            self._failures = 0
            self.last_error = None
            return frame

        self._failures += 1
        if self._failures >= 3:
            self._rotate_url()
            self.close_stream()
            if not self._connect_mjpeg() and self._mode == "mjpeg":
                pass
        return None

    def close_stream(self):
        self._chunk_iter = None
        if self._resp is not None:
            self._resp.close()
            self._resp = None
        self._buffer = b""

    def close(self):
        self.close_stream()
        self._session.close()


# Совместимость со старыми импортами
RTSPReader = None  # set below after class def
mask_rtsp_url = mask_stream_url


class CameraReader:
    """Читает кадры с HTTP-камеры или локального видеофайла."""

    def __init__(self, camera_id: int, source: str):
        self.camera_id = camera_id
        self.source = source
        self._http: _DahuaHttpReader | None = None
        self._cap: cv2.VideoCapture | None = None
        self._last_read_time = 0.0
        self.is_online = False
        self.last_error: str | None = None

        if source.startswith("http"):
            self._http = _DahuaHttpReader(source)
            logger.info("Camera %s: HTTP mode %s", camera_id, mask_stream_url(source))
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
            if self.last_error:
                logger.warning(
                    "Camera %s: %s — %s",
                    self.camera_id,
                    mask_stream_url(self.source),
                    self.last_error,
                )
            time.sleep(1)
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
