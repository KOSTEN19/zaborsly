from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


class CameraOut(BaseModel):
    id: int
    name: str
    rtsp_url: str
    position: int
    is_active: bool
    is_online: bool
    last_seen_at: datetime | None

    model_config = {"from_attributes": True}


class DetectionOut(BaseModel):
    id: int
    camera_id: int
    camera_name: str | None = None
    plate: str
    confidence: float
    direction: str
    detected_at: datetime
    photo_url: str

    model_config = {"from_attributes": True}


class VehicleSessionOut(BaseModel):
    id: int
    plate: str
    entry_at: datetime | None
    exit_at: datetime | None
    entry_photo_url: str | None
    exit_photo_url: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedDetections(BaseModel):
    items: list[DetectionOut]
    total: int
    page: int
    page_size: int


class PaginatedSessions(BaseModel):
    items: list[VehicleSessionOut]
    total: int
    page: int
    page_size: int


class DashboardStats(BaseModel):
    entries_today: int
    exits_today: int
    on_site: int
    detections_today: int
    cameras: list[CameraOut]


class SettingsOut(BaseModel):
    single_camera_mode: bool
    camera_1_name: str
    camera_2_name: str
    camera_1_rtsp: str
    camera_2_rtsp: str
    cam1_to_cam2_direction: Literal["entry", "exit"]
    movement_window_sec: int
    detection_cooldown_sec: int
    min_confidence: float
    min_confirmed_confidence: float
    live_preview_interval_ms: int
    live_max_frame_width: int
    anpr_max_frame_width: int
    anpr_min_interval_ms: int
    enable_clahe: bool
    motion_min_area_ratio: float
    plate_vote_required: int
    plate_vote_window: int
    torch_num_threads: int


class CameraLiveStatus(BaseModel):
    camera_id: int
    camera_name: str
    plate: str | None
    confidence: float | None
    detected_at: str | None
    online: bool
