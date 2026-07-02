from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Detection, Direction, SessionStatus, VehicleSession
from app.services.direction import PendingDetection


class SessionManager:
    def record_detection(
        self,
        db: Session,
        camera_id: int,
        plate: str,
        confidence: float,
        direction: Direction,
        photo_path: str,
        detected_at: datetime,
    ) -> Detection:
        detection = Detection(
            camera_id=camera_id,
            plate=plate,
            confidence=confidence,
            direction=direction,
            photo_path=photo_path,
            detected_at=detected_at,
        )
        db.add(detection)
        db.flush()
        return detection

    def handle_single_camera_pass(
        self,
        db: Session,
        camera_id: int,
        plate: str,
        confidence: float,
        photo_path: str,
        detected_at: datetime,
    ) -> Detection:
        """One camera: toggle entry/exit by open session (on_site → exit, else → entry)."""
        open_session = (
            db.query(VehicleSession)
            .filter(
                VehicleSession.plate == plate,
                VehicleSession.status == SessionStatus.on_site,
            )
            .order_by(VehicleSession.entry_at.desc())
            .first()
        )

        if open_session:
            direction = Direction.exit
            open_session.exit_at = detected_at
            open_session.exit_photo = photo_path
            open_session.status = SessionStatus.completed
        else:
            direction = Direction.entry
            db.add(
                VehicleSession(
                    plate=plate,
                    entry_at=detected_at,
                    entry_photo=photo_path,
                    status=SessionStatus.on_site,
                )
            )

        return self.record_detection(
            db=db,
            camera_id=camera_id,
            plate=plate,
            confidence=confidence,
            direction=direction,
            photo_path=photo_path,
            detected_at=detected_at,
        )

    def handle_direction_pair(
        self,
        db: Session,
        direction: Direction,
        first: PendingDetection,
        second: PendingDetection,
    ) -> VehicleSession | None:
        if direction == Direction.entry:
            session = VehicleSession(
                plate=first.plate,
                entry_at=first.detected_at,
                entry_photo=first.photo_path,
                status=SessionStatus.on_site,
            )
            db.add(session)
            db.flush()
            return session

        if direction == Direction.exit:
            session = (
                db.query(VehicleSession)
                .filter(
                    VehicleSession.plate == first.plate,
                    VehicleSession.status == SessionStatus.on_site,
                )
                .order_by(VehicleSession.entry_at.desc())
                .first()
            )
            if session:
                session.exit_at = second.detected_at
                session.exit_photo = second.photo_path
                session.status = SessionStatus.completed
            else:
                session = VehicleSession(
                    plate=first.plate,
                    exit_at=second.detected_at,
                    exit_photo=second.photo_path,
                    status=SessionStatus.unknown,
                )
                db.add(session)
            db.flush()
            return session

        return None


session_manager = SessionManager()
