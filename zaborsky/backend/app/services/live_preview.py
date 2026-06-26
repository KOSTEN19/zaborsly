import json
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import cv2
import numpy as np

from app.config import settings

logger = __import__("logging").getLogger(__name__)


@dataclass
class LiveStatus:
    plate: str | None = None
    confidence: float | None = None
    detected_at: str | None = None
    online: bool = False


class LivePreviewService:
    def __init__(self):
        self._locks: dict[int, threading.Lock] = {}
        self._last_plate: dict[int, tuple[str, float, datetime]] = {}

    def _live_dir(self) -> str:
        path = os.path.join(settings.photo_dir, "live")
        os.makedirs(path, exist_ok=True)
        return path

    def _lock(self, camera_id: int) -> threading.Lock:
        if camera_id not in self._locks:
            self._locks[camera_id] = threading.Lock()
        return self._locks[camera_id]

    def _jpg_path(self, camera_id: int) -> str:
        return os.path.join(self._live_dir(), f"camera_{camera_id}.jpg")

    def _json_path(self, camera_id: int) -> str:
        return os.path.join(self._live_dir(), f"camera_{camera_id}.json")

    def _write_status(self, camera_id: int, status: LiveStatus):
        with open(self._json_path(camera_id), "w", encoding="utf-8") as f:
            json.dump(asdict(status), f, ensure_ascii=False)

    def update_frame(
        self,
        camera_id: int,
        frame: np.ndarray,
        plate: str | None = None,
        confidence: float | None = None,
    ):
        now = datetime.now(timezone.utc)
        if plate and confidence is not None:
            self._last_plate[camera_id] = (plate, confidence, now)

        display_plate: str | None = None
        display_conf: float | None = None
        display_at: str | None = None
        last = self._last_plate.get(camera_id)
        if last:
            p, c, ts = last
            if (now - ts).total_seconds() <= settings.live_plate_ttl_sec:
                display_plate = p
                display_conf = c
                display_at = ts.isoformat()

        status = LiveStatus(
            plate=display_plate,
            confidence=display_conf,
            detected_at=display_at,
            online=True,
        )

        with self._lock(camera_id):
            cv2.imwrite(self._jpg_path(camera_id), frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            self._write_status(camera_id, status)

    def set_offline(self, camera_id: int):
        status = self.get_status(camera_id)
        status.online = False
        with self._lock(camera_id):
            self._write_status(camera_id, status)

    def get_snapshot_path(self, camera_id: int) -> str | None:
        path = self._jpg_path(camera_id)
        return path if os.path.isfile(path) else None

    def get_status(self, camera_id: int) -> LiveStatus:
        path = self._json_path(camera_id)
        if not os.path.isfile(path):
            return LiveStatus(online=False)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return LiveStatus(**data)
        except (json.JSONDecodeError, TypeError):
            return LiveStatus(online=False)


live_preview = LivePreviewService()
