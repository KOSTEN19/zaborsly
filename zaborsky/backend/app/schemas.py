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
    camera_1_http: str = ""
    camera_2_http: str = ""
    camera_1_roi: str = ""
    camera_2_roi: str = ""
    cam1_to_cam2_direction: Literal["entry", "exit"]
    movement_window_sec: int
    detection_cooldown_sec: int
    min_confidence: float
    min_confirmed_confidence: float
    live_preview_interval_ms: int
    live_max_frame_width: int
    live_plate_ttl_sec: int = 10
    anpr_max_frame_width: int
    anpr_min_interval_ms: int
    enable_clahe: bool
    motion_min_area_ratio: float
    motion_tail_sec: float = 2.5
    plate_vote_required: int
    plate_vote_window: int
    torch_num_threads: int


class SettingsUpdate(BaseModel):
    camera_1_name: str
    camera_2_name: str = ""
    camera_1_rtsp: str = ""
    camera_2_rtsp: str = ""
    camera_1_http: str = ""
    camera_2_http: str = ""
    camera_1_roi: str = ""
    camera_2_roi: str = ""
    cam1_to_cam2_direction: Literal["entry", "exit"] = "entry"
    movement_window_sec: int = Field(ge=5, le=300)
    detection_cooldown_sec: int = Field(ge=5, le=600)
    min_confidence: float = Field(ge=0.1, le=1.0)
    min_confirmed_confidence: float = Field(ge=0.1, le=1.0)
    live_preview_interval_ms: int = Field(ge=100, le=5000)
    live_max_frame_width: int = Field(ge=320, le=1920)
    live_plate_ttl_sec: int = Field(ge=1, le=120)
    anpr_max_frame_width: int = Field(ge=640, le=3840)
    anpr_min_interval_ms: int = Field(ge=100, le=10000)
    enable_clahe: bool = True
    motion_min_area_ratio: float = Field(ge=0.0001, le=0.1)
    motion_tail_sec: float = Field(ge=0.5, le=30.0)
    plate_vote_required: int = Field(ge=1, le=10)
    plate_vote_window: int = Field(ge=2, le=20)
    torch_num_threads: int = Field(ge=1, le=8)


class VerifyPasswordRequest(BaseModel):
    password: str


class VerifyPasswordResponse(BaseModel):
    valid: bool


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


class CameraLiveStatus(BaseModel):
    camera_id: int
    camera_name: str
    plate: str | None
    confidence: float | None
    detected_at: str | None
    online: bool
