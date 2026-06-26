from dataclasses import dataclass
from datetime import datetime, timedelta

from app.config import settings
from app.models import Direction


@dataclass
class PendingDetection:
    plate: str
    camera_id: int
    detected_at: datetime
    photo_path: str
    confidence: float


@dataclass
class DirectionPair:
    first: PendingDetection
    second: PendingDetection


class DirectionTracker:
    def __init__(self):
        self._pending: dict[str, PendingDetection] = {}
        self._cooldown: dict[tuple[int, str], datetime] = {}

    def _is_on_cooldown(self, camera_id: int, plate: str, now: datetime) -> bool:
        key = (camera_id, plate)
        last = self._cooldown.get(key)
        if last and (now - last).total_seconds() < settings.detection_cooldown_sec:
            return True
        return False

    def _set_cooldown(self, camera_id: int, plate: str, now: datetime):
        self._cooldown[(camera_id, plate)] = now

    def process(
        self, plate: str, camera_id: int, detected_at: datetime, photo_path: str, confidence: float
    ) -> tuple[Direction, DirectionPair | None]:
        if self._is_on_cooldown(camera_id, plate, detected_at):
            return Direction.unknown, None

        self._set_cooldown(camera_id, plate, detected_at)

        pending = self._pending.get(plate)
        if pending is None:
            self._pending[plate] = PendingDetection(
                plate=plate,
                camera_id=camera_id,
                detected_at=detected_at,
                photo_path=photo_path,
                confidence=confidence,
            )
            return Direction.unknown, None

        window = timedelta(seconds=settings.movement_window_sec)
        if detected_at - pending.detected_at > window:
            self._pending[plate] = PendingDetection(
                plate=plate,
                camera_id=camera_id,
                detected_at=detected_at,
                photo_path=photo_path,
                confidence=confidence,
            )
            return Direction.unknown, None

        if pending.camera_id == camera_id:
            return Direction.unknown, None

        direction = self._resolve_direction(pending.camera_id, camera_id)
        pair = DirectionPair(
            first=pending,
            second=PendingDetection(
                plate=plate,
                camera_id=camera_id,
                detected_at=detected_at,
                photo_path=photo_path,
                confidence=confidence,
            ),
        )
        del self._pending[plate]
        return direction, pair

    def _resolve_direction(self, first_cam: int, second_cam: int) -> Direction:
        if first_cam == 1 and second_cam == 2:
            return (
                Direction.entry
                if settings.cam1_to_cam2_direction == "entry"
                else Direction.exit
            )
        if first_cam == 2 and second_cam == 1:
            return (
                Direction.exit
                if settings.cam1_to_cam2_direction == "entry"
                else Direction.entry
            )
        return Direction.unknown
