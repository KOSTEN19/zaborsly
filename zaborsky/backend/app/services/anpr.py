import logging
import threading
from dataclasses import dataclass

import numpy as np

from app.config import settings
from app.services.plate_utils import is_valid_ru_plate, normalize_plate

logger = logging.getLogger(__name__)

_inference_lock = threading.Lock()


@dataclass
class PlateResult:
    plate: str
    confidence: float


class ANPRService:
    def __init__(self):
        self._pipeline = None
        self._unzip = None
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return

        import torch
        from nomeroff_net import pipeline
        from nomeroff_net.tools import unzip

        torch.set_num_threads(settings.torch_num_threads)
        if hasattr(torch, "set_num_interop_threads"):
            torch.set_num_interop_threads(max(1, settings.torch_num_threads // 2))

        logger.info("Loading nomeroff_net pipeline (torch threads=%s)...", settings.torch_num_threads)
        self._pipeline = pipeline("number_plate_detection_and_reading", image_loader="opencv")
        self._unzip = unzip
        self._initialized = True
        logger.info("nomeroff_net pipeline loaded")

    def recognize(self, frame: np.ndarray) -> list[PlateResult]:
        if not self._initialized:
            self.initialize()

        try:
            with _inference_lock:
                (_, _, _, _, _, _, _, confidences, texts) = self._unzip(self._pipeline([frame]))

            results: list[PlateResult] = []
            for text, conf in zip(texts, confidences):
                if not text:
                    continue
                plate = normalize_plate(str(text))
                if not is_valid_ru_plate(plate):
                    continue
                confidence = float(conf) if conf is not None else 0.5
                if confidence < settings.min_confidence:
                    continue
                results.append(PlateResult(plate=plate, confidence=confidence))
            return results
        except Exception as e:
            logger.exception("ANPR recognition error: %s", e)
            return []


anpr_service = ANPRService()
