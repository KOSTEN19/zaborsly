import logging

from app.auth import hash_password
from app.config import settings
from app.database import SessionLocal
from app.models import Camera, User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")


def seed():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == settings.admin_username).first()
        if not admin:
            admin = User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
            )
            db.add(admin)
            logger.info("Created admin user: %s", settings.admin_username)

        cameras = [
            (1, settings.camera_1_name, settings.camera_1_rtsp or settings.video_file_1, True),
        ]
        if settings.camera_2_configured():
            cameras.append(
                (2, settings.camera_2_name, settings.camera_2_rtsp or settings.video_file_2, True)
            )

        for position, name, rtsp, active in cameras:
            cam = db.query(Camera).filter(Camera.position == position).first()
            if not cam:
                cam = Camera(name=name, rtsp_url=rtsp or "", position=position, is_active=active)
                db.add(cam)
                logger.info("Created camera %s: %s", position, name)
            else:
                cam.name = name
                cam.rtsp_url = rtsp or ""
                cam.is_active = active

        if not settings.camera_2_configured():
            cam2 = db.query(Camera).filter(Camera.position == 2).first()
            if cam2:
                cam2.is_active = False
                cam2.rtsp_url = ""

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
