from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://zaborsky:change_me@postgres:5432/zaborsky"

    admin_username: str = "admin"
    admin_password: str = "admin"
    jwt_secret: str = "change_me_jwt_secret_min_32_chars_long"
    jwt_expire_minutes: int = 1440

    camera_1_rtsp: str = ""
    camera_2_rtsp: str = ""
    camera_1_http: str = ""
    camera_2_http: str = ""
    camera_1_name: str = "Камера 1"
    camera_2_name: str = "Камера 2"
    camera_1_roi: str = ""
    camera_2_roi: str = ""
    video_file_1: str = ""
    video_file_2: str = ""

    # Dahua/Hikvision often need TCP; UDP fails silently in OpenCV/ffmpeg
    rtsp_use_tcp: bool = True
    rtsp_open_timeout_sec: int = 10

    cam1_to_cam2_direction: str = "entry"
    movement_window_sec: int = 30
    detection_cooldown_sec: int = 60

    # Per-frame threshold (lower — voter confirms across frames)
    min_confidence: float = 0.45
    min_confirmed_confidence: float = 0.55

    # Live preview (fast, low CPU)
    live_preview_interval_ms: int = 300
    live_max_frame_width: int = 960
    live_plate_ttl_sec: int = 10

    # ANPR (high quality, runs only on motion)
    anpr_max_frame_width: int = 1920
    anpr_min_interval_ms: int = 400
    enable_clahe: bool = True

    # Motion gate — skip ANPR when nothing moves
    motion_min_area_ratio: float = 0.004
    motion_tail_sec: float = 2.5

    # Multi-frame voting for accuracy
    plate_vote_required: int = 2
    plate_vote_window: int = 5

    torch_num_threads: int = 2

    photo_dir: str = "/data/photos"

    def camera_2_configured(self) -> bool:
        return bool(self.camera_2_http or self.camera_2_rtsp or self.video_file_2)

    def single_camera_mode(self) -> bool:
        return not self.camera_2_configured()


settings = Settings()
