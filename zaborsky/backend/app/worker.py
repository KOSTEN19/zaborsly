import logging
import threading
import time

from app.config import settings
from app.database import SessionLocal
from app.models import Camera
from app.services.anpr import anpr_service
from app.services.direction import DirectionTracker
from app.services.frame_preprocess import prepare_anpr_frame, prepare_live_frame
from app.services.live_preview import live_preview
from app.services.motion_detector import MotionDetector
from app.services.plate_voter import PlateVoter
from app.services.plate_utils import utcnow
from app.services.rtsp_reader import RTSPReader, get_camera_sources, save_frame
from app.services.session_manager import session_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("worker")


def update_camera_status(camera_id: int, online: bool):
    db = SessionLocal()
    try:
        camera = db.query(Camera).filter(Camera.id == camera_id).first()
        if camera:
            camera.is_online = online
            if online:
                camera.last_seen_at = utcnow()
            db.commit()
    finally:
        db.close()


def handle_detection(camera_id: int, plate: str, confidence: float, photo_path: str, tracker: DirectionTracker):
    now = utcnow()
    direction, pair = tracker.process(
        plate=plate,
        camera_id=camera_id,
        detected_at=now,
        photo_path=photo_path,
        confidence=confidence,
    )

    db = SessionLocal()
    try:
        session_manager.record_detection(
            db=db,
            camera_id=camera_id,
            plate=plate,
            confidence=confidence,
            direction=direction,
            photo_path=photo_path,
            detected_at=now,
        )

        if pair is not None and direction.value != "unknown":
            session_manager.handle_direction_pair(db, direction, pair.first, pair.second)
            logger.info(
                "Direction %s for plate %s (cam %s -> cam %s)",
                direction.value,
                plate,
                pair.first.camera_id,
                pair.second.camera_id,
            )

        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Error saving detection for camera %s", camera_id)
    finally:
        db.close()


def process_camera(camera_id: int, source: str, roi: str | None, tracker: DirectionTracker):
    reader = RTSPReader(camera_id, source)
    motion = MotionDetector()
    voter = PlateVoter()
    was_active = False

    logger.info("Started processing camera %s: %s", camera_id, source)

    while True:
        raw = reader.read_raw()
        if raw is None:
            if not reader.is_online:
                update_camera_status(camera_id, False)
                live_preview.set_offline(camera_id)
            time.sleep(0.02)
            continue

        update_camera_status(camera_id, True)

        motion.has_motion(raw)
        active = motion.is_scene_active()
        if was_active and not active:
            voter.reset_episode()
        was_active = active

        # Fast live preview path (no ANPR)
        live_frame = prepare_live_frame(raw)
        recent = voter.best_recent()
        live_preview.update_frame(
            camera_id,
            live_frame,
            recent.plate if recent else None,
            recent.confidence if recent else None,
        )

        # ANPR only when motion detected (saves ~70-90% CPU when idle)
        if not motion.should_run_anpr(raw):
            continue

        anpr_frame = prepare_anpr_frame(raw, roi)
        results = anpr_service.recognize(anpr_frame)

        display = voter.best_recent()
        if results:
            display = max(results, key=lambda r: r.confidence)
            live_preview.update_frame(camera_id, live_frame, display.plate, display.confidence)

        confirmed = voter.add(results)
        if confirmed is None:
            continue

        photo_path = save_frame(anpr_frame)
        logger.info(
            "Confirmed plate %s (%.0f%%, %d votes) on camera %s",
            confirmed.plate,
            confirmed.confidence * 100,
            confirmed.votes,
            camera_id,
        )
        handle_detection(camera_id, confirmed.plate, confirmed.confidence, photo_path, tracker)


def wait_for_camera_sources() -> list:
    while True:
        sources = get_camera_sources()
        if sources:
            return sources
        logger.error(
            "Камеры не настроены. Задайте CAMERA_1_RTSP/CAMERA_2_RTSP "
            "или VIDEO_FILE_1/VIDEO_FILE_2 в .env и перезапустите worker."
        )
        time.sleep(30)


def run_worker():
    anpr_service.initialize()

    tracker = DirectionTracker()
    sources = wait_for_camera_sources()

    threads = []
    for src in sources:
        t = threading.Thread(
            target=process_camera,
            args=(src.camera_id, src.source, src.roi, tracker),
            daemon=True,
        )
        t.start()
        threads.append(t)

    logger.info(
        "Worker started: %d camera(s), live=%dms, anpr_max=%dpx, motion_gate=on, vote=%d/%d",
        len(threads),
        settings.live_preview_interval_ms,
        settings.anpr_max_frame_width,
        settings.plate_vote_required,
        settings.plate_vote_window,
    )

    while True:
        time.sleep(60)


if __name__ == "__main__":
    run_worker()
