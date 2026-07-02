from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, verify_password
from app.config import settings
from app.database import get_db
from app.models import Camera, Detection, SessionStatus, User, VehicleSession
from app.schemas import (
    CameraOut,
    DashboardStats,
    DetectionOut,
    PaginatedDetections,
    PaginatedSessions,
    SettingsOut,
    TokenResponse,
    VehicleSessionOut,
)

router = APIRouter()


def _photo_url(path: str | None) -> str | None:
    if not path:
        return None
    return f"/api/photos/{path}"


@router.post("/auth/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return TokenResponse(access_token=create_access_token(user.username))


@router.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return {"username": user.username}


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/dashboard", response_model=DashboardStats)
def dashboard(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    now_date = func.current_date()

    entries_today = (
        db.query(func.count(VehicleSession.id))
        .filter(
            VehicleSession.entry_at.isnot(None),
            func.date(VehicleSession.entry_at) == now_date,
        )
        .scalar()
        or 0
    )
    exits_today = (
        db.query(func.count(VehicleSession.id))
        .filter(
            VehicleSession.exit_at.isnot(None),
            func.date(VehicleSession.exit_at) == now_date,
        )
        .scalar()
        or 0
    )
    on_site = (
        db.query(func.count(VehicleSession.id))
        .filter(VehicleSession.status == SessionStatus.on_site)
        .scalar()
        or 0
    )
    detections_today = (
        db.query(func.count(Detection.id))
        .filter(func.date(Detection.detected_at) == now_date)
        .scalar()
        or 0
    )
    cameras = (
        db.query(Camera)
        .filter(Camera.is_active.is_(True))
        .order_by(Camera.position)
        .all()
    )

    return DashboardStats(
        entries_today=entries_today,
        exits_today=exits_today,
        on_site=on_site,
        detections_today=detections_today,
        cameras=[CameraOut.model_validate(c) for c in cameras],
    )


@router.get("/cameras", response_model=list[CameraOut])
def list_cameras(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return (
        db.query(Camera)
        .filter(Camera.is_active.is_(True))
        .order_by(Camera.position)
        .all()
    )


@router.get("/detections", response_model=PaginatedDetections)
def list_detections(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    plate: str | None = None,
    camera_id: int | None = None,
):
    query = db.query(Detection)
    if plate:
        query = query.filter(Detection.plate.ilike(f"%{plate.upper()}%"))
    if camera_id:
        query = query.filter(Detection.camera_id == camera_id)

    total = query.count()
    items = (
        query.order_by(Detection.detected_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    camera_map = {c.id: c.name for c in db.query(Camera).all()}
    result = []
    for d in items:
        out = DetectionOut(
            id=d.id,
            camera_id=d.camera_id,
            camera_name=camera_map.get(d.camera_id),
            plate=d.plate,
            confidence=d.confidence,
            direction=d.direction.value,
            detected_at=d.detected_at,
            photo_url=_photo_url(d.photo_path),
        )
        result.append(out)

    return PaginatedDetections(items=result, total=total, page=page, page_size=page_size)


@router.get("/sessions", response_model=PaginatedSessions)
def list_sessions(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    plate: str | None = None,
    status: str | None = None,
):
    query = db.query(VehicleSession)
    if plate:
        query = query.filter(VehicleSession.plate.ilike(f"%{plate.upper()}%"))
    if status:
        query = query.filter(VehicleSession.status == status)

    total = query.count()
    items = (
        query.order_by(VehicleSession.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    result = [
        VehicleSessionOut(
            id=s.id,
            plate=s.plate,
            entry_at=s.entry_at,
            exit_at=s.exit_at,
            entry_photo_url=_photo_url(s.entry_photo),
            exit_photo_url=_photo_url(s.exit_photo),
            status=s.status.value,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in items
    ]
    return PaginatedSessions(items=result, total=total, page=page, page_size=page_size)


@router.get("/settings", response_model=SettingsOut)
def get_settings(_: User = Depends(get_current_user)):
    return SettingsOut(
        single_camera_mode=settings.single_camera_mode(),
        camera_1_name=settings.camera_1_name,
        camera_2_name=settings.camera_2_name,
        camera_1_rtsp=settings.camera_1_rtsp or settings.video_file_1 or "(не задано)",
        camera_2_rtsp=settings.camera_2_rtsp or settings.video_file_2 or "(не задано)",
        cam1_to_cam2_direction=settings.cam1_to_cam2_direction,  # type: ignore[arg-type]
        movement_window_sec=settings.movement_window_sec,
        detection_cooldown_sec=settings.detection_cooldown_sec,
        min_confidence=settings.min_confidence,
        min_confirmed_confidence=settings.min_confirmed_confidence,
        live_preview_interval_ms=settings.live_preview_interval_ms,
        live_max_frame_width=settings.live_max_frame_width,
        anpr_max_frame_width=settings.anpr_max_frame_width,
        anpr_min_interval_ms=settings.anpr_min_interval_ms,
        enable_clahe=settings.enable_clahe,
        motion_min_area_ratio=settings.motion_min_area_ratio,
        plate_vote_required=settings.plate_vote_required,
        plate_vote_window=settings.plate_vote_window,
        torch_num_threads=settings.torch_num_threads,
    )
