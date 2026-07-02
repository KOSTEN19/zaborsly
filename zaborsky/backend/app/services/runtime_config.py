import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings as env
from app.database import SessionLocal
from app.models import AppConfig, Camera

logger = logging.getLogger(__name__)

ENV_FALLBACK_KEYS = frozenset(
    {
        "camera_1_rtsp",
        "camera_2_rtsp",
        "camera_1_name",
        "camera_2_name",
    }
)

EDITABLE_KEYS = (
    "camera_1_rtsp",
    "camera_2_rtsp",
    "camera_1_name",
    "camera_2_name",
    "camera_1_roi",
    "camera_2_roi",
    "cam1_to_cam2_direction",
    "movement_window_sec",
    "detection_cooldown_sec",
    "min_confidence",
    "min_confirmed_confidence",
    "live_preview_interval_ms",
    "live_max_frame_width",
    "live_plate_ttl_sec",
    "anpr_max_frame_width",
    "anpr_min_interval_ms",
    "enable_clahe",
    "motion_min_area_ratio",
    "motion_tail_sec",
    "plate_vote_required",
    "plate_vote_window",
    "torch_num_threads",
)

_cache: dict | None = None


def _env_defaults() -> dict:
    return {key: getattr(env, key) for key in EDITABLE_KEYS}


def _load_row(db: Session) -> AppConfig | None:
    return db.query(AppConfig).filter(AppConfig.id == 1).first()


def reload(db: Session | None = None) -> dict:
    global _cache
    merged = _env_defaults()
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        row = _load_row(db)
        if row and row.data:
            for key, value in row.data.items():
                if key not in EDITABLE_KEYS:
                    continue
                if key in ENV_FALLBACK_KEYS and value in (None, ""):
                    continue
                merged[key] = value
    finally:
        if own_session:
            db.close()
    _cache = merged
    return _cache


def get_dict() -> dict:
    if _cache is None:
        reload()
    return dict(_cache or {})


def single_camera_mode(data: dict | None = None) -> bool:
    d = data or get_dict()
    return not bool(d.get("camera_2_rtsp"))


def to_settings_out() -> dict:
    d = get_dict()
    return {
        "single_camera_mode": single_camera_mode(d),
        **{k: d[k] for k in EDITABLE_KEYS if k in d},
        "camera_1_rtsp": d.get("camera_1_rtsp") or env.video_file_1 or "",
        "camera_2_rtsp": d.get("camera_2_rtsp") or env.video_file_2 or "",
    }


def save(db: Session, payload: dict) -> dict:
    global _cache
    current = get_dict()
    updated = {**current}
    for key in EDITABLE_KEYS:
        if key in payload:
            updated[key] = payload[key]

    if updated.get("cam1_to_cam2_direction") not in ("entry", "exit"):
        updated["cam1_to_cam2_direction"] = "entry"

    row = _load_row(db)
    if not row:
        row = AppConfig(id=1, data={})
        db.add(row)
    row.data = updated
    row.updated_at = datetime.now(timezone.utc)
    _sync_cameras(db, updated)
    db.flush()
    _cache = updated
    return updated


def _sync_cameras(db: Session, data: dict):
    cam1 = db.query(Camera).filter(Camera.position == 1).first()
    if not cam1:
        cam1 = Camera(name=data["camera_1_name"], position=1)
        db.add(cam1)
    cam1.name = data["camera_1_name"]
    cam1.rtsp_url = data.get("camera_1_rtsp") or ""
    cam1.is_active = True

    cam2 = db.query(Camera).filter(Camera.position == 2).first()
    if single_camera_mode(data):
        if cam2:
            cam2.is_active = False
            cam2.rtsp_url = ""
    else:
        if not cam2:
            cam2 = Camera(name=data["camera_2_name"], position=2)
            db.add(cam2)
        cam2.name = data["camera_2_name"]
        cam2.rtsp_url = data.get("camera_2_rtsp") or ""
        cam2.is_active = True


def ensure_row(db: Session):
    row = _load_row(db)
    if not row:
        row = AppConfig(id=1, data=_env_defaults())
        db.add(row)
        db.flush()
    else:
        defaults = _env_defaults()
        data = dict(row.data or {})
        changed = False
        for key in ENV_FALLBACK_KEYS:
            if not data.get(key) and defaults.get(key):
                data[key] = defaults[key]
                changed = True
        if changed:
            row.data = data
            row.updated_at = datetime.now(timezone.utc)
            db.flush()
    reload(db)


class RuntimeConfig:
    def __getattr__(self, name: str):
        if name in ("single_camera_mode", "camera_2_configured"):
            return getattr(self, name)()
        d = get_dict()
        if name in d:
            return d[name]
        return getattr(env, name)

    def single_camera_mode(self) -> bool:
        return single_camera_mode()

    def camera_2_configured(self) -> bool:
        return not single_camera_mode()


cfg = RuntimeConfig()
