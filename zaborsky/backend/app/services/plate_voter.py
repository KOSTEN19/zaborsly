from collections import deque
from dataclasses import dataclass

from app.services.runtime_config import cfg
from app.services.anpr import PlateResult


@dataclass
class VotedPlate:
    plate: str
    confidence: float
    votes: int


class PlateVoter:
    """Confirm plate across multiple frames — fewer false positives, higher accuracy."""

    def __init__(self):
        self._history: deque[tuple[str, float]] = deque(maxlen=cfg.plate_vote_window)
        self._last_emitted: str | None = None

    def add(self, results: list[PlateResult]) -> VotedPlate | None:
        if results:
            best = max(results, key=lambda r: r.confidence)
            self._history.append((best.plate, best.confidence))

        confirmed = self._check_confirmed()
        if confirmed is None:
            return None

        if confirmed.plate == self._last_emitted:
            return None

        self._last_emitted = confirmed.plate
        self._history.clear()
        return confirmed

    def reset_episode(self):
        """Call when motion stops — allow same plate on next vehicle pass."""
        self._last_emitted = None
        self._history.clear()

    def best_recent(self) -> PlateResult | None:
        if not self._history:
            return None
        plate, conf = self._history[-1]
        return PlateResult(plate=plate, confidence=conf)

    def _check_confirmed(self) -> VotedPlate | None:
        if len(self._history) < cfg.plate_vote_required:
            return None

        counts: dict[str, list[float]] = {}
        for plate, conf in self._history:
            counts.setdefault(plate, []).append(conf)

        best_plate = ""
        best_votes = 0
        best_confs: list[float] = []
        for plate, confs in counts.items():
            if len(confs) > best_votes:
                best_votes = len(confs)
                best_plate = plate
                best_confs = confs

        if best_votes < cfg.plate_vote_required:
            return None

        avg_conf = sum(best_confs) / len(best_confs)
        if avg_conf < cfg.min_confirmed_confidence:
            return None

        return VotedPlate(plate=best_plate, confidence=avg_conf, votes=best_votes)
