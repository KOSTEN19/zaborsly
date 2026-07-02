from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.auth import get_current_user
from app.config import settings
from app.models import User

router = APIRouter()


@router.get("/photos/{path:path}")
def get_photo(path: str, _: User = Depends(get_current_user)):
    safe_path = Path(settings.photo_dir) / path
    resolved = safe_path.resolve()
    base = Path(settings.photo_dir).resolve()
    if not str(resolved).startswith(str(base)):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(resolved)
