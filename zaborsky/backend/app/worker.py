import logging
import threading
import time

from app.services.runtime_config import cfg, reload as reload_runtime
from app.database import SessionLocal
from app.models import Camera
from app.services.anpr import anpr_service
from app.services.direction import DirectionTracker
from app.services.frame_preprocess import prepare_anpr_frame, prepare_live_frame
from app.services.live_preview import live_preview
from app.services.motion_detector import MotionDetector
from app.services.plate_voter import PlateVoter
from app.services.plate_utils import utcnow
from app.services.rtsp_reader import RTSPReader, get_camera_sources, mask_rtsp_url, save_frame
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


def handle_detection(
    camera_id: int,
    plate: str,
    confidence: float,
    photo_path: str,
    tracker: DirectionTracker,
    *,
    single_camera: bool,
):
    now = utcnow()

    db = SessionLocal()
    try:
        if single_camera:
            if not tracker.try_acquire(plate, camera_id, now):
                return
            detection = session_manager.handle_single_camera_pass(
                db=db,
                camera_id=camera_id,
                plate=plate,
                confidence=confidence,
                photo_path=photo_path,
                detected_at=now,
            )
            logger.info(
                "Single-cam %s plate %s → %s",
                camera_id,
                plate,
                detection.direction.value,
            )
        else:
            direction, pair = tracker.process(
                plate=plate,
                camera_id=camera_id,
                detected_at=now,
                photo_path=photo_path,
                confidence=confidence,
            )
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


def process_camera(camera_id: int, source: str, roi: str | None, tracker: DirectionTracker, *, single_camera: bool):
    reader = RTSPReader(camera_id, source)
    motion = MotionDetector()
    voter = PlateVoter()
    was_active = False

    logger.info("Started processing camera %s: %s", camera_id, mask_rtsp_url(source))

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

        live_frame = prepare_live_frame(raw)
        recent = voter.best_recent()
        live_preview.update_frame(
            camera_id,
            live_frame,
            recent.plate if recent else None,
            recent.confidence if recent else None,
        )

        if not motion.should_run_anpr(raw):
            continue

        anpr_frame = prepare_anpr_frame(raw, roi)
        results = anpr_service.recognize(anpr_frame)

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
        handle_detection(
            camera_id,
            confirmed.plate,
            confirmed.confidence,
            photo_path,
            tracker,
            single_camera=single_camera,
        )


def wait_for_camera_sources() -> list:
    while True:
        reload_runtime()
        sources = get_camera_sources()
        if sources:
            for src in sources:
                logger.info(
                    "Camera source id=%s: %s",
                    src.camera_id,
                    mask_rtsp_url(src.source),
                )
            return sources
        logger.error(
            "Камера не настроена. Задайте CAMERA_1_RTSP в .env или в админке → Настройки, "
            "затем: docker compose restart worker"
        )
        time.sleep(30)


def run_worker():
    reload_runtime()
    anpr_service.initialize()

    tracker = DirectionTracker()
    sources = wait_for_camera_sources()
    single_camera = cfg.single_camera_mode()

    threads = []
    for src in sources:
        t = threading.Thread(
            target=process_camera,
            args=(src.camera_id, src.source, src.roi, tracker),
            kwargs={"single_camera": single_camera},
            daemon=True,
        )
        t.start()
        threads.append(t)

    mode = "single (въезд/выезд по сессии)" if single_camera else "dual (по двум камерам)"
    logger.info(
        "Worker started: %d camera(s), mode=%s, live=%dms, anpr_max=%dpx",
        len(threads),
        mode,
        cfg.live_preview_interval_ms,
        cfg.anpr_max_frame_width,
    )

    while True:
        reload_runtime()
        time.sleep(30)


if __name__ == "__main__":
    run_worker()
