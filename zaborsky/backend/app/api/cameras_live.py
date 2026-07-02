from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.auth import get_current_user
from app.models import Camera, User
from app.schemas import CameraLiveStatus
from app.services.live_preview import live_preview
from sqlalchemy.orm import Session

from app.database import get_db

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.get("/{camera_id}/live", response_model=CameraLiveStatus)
def camera_live_status(
    camera_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    status = live_preview.get_status(camera_id)
    return CameraLiveStatus(
        camera_id=camera_id,
        camera_name=camera.name,
        plate=status.plate,
        confidence=status.confidence,
        detected_at=status.detected_at,
        online=status.online or camera.is_online,
    )


@router.get("/{camera_id}/snapshot")
def camera_snapshot(
    camera_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
    t: str | None = Query(default=None),
):
    camera = db.query(Camera).filter(Camera.id == camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    path = live_preview.get_snapshot_path(camera_id)
    if not path:
        raise HTTPException(status_code=404, detail="No live frame yet")

    return FileResponse(path, media_type="image/jpeg")
