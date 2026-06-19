import time
from pathlib import Path

import cv2
import numpy as np

from ..models import SourceMeta, SourceType
from ..utils import LOGGER, ensure_bgr
from .base import BaseReader

# ─────────────────────────────────────────────────────────────────────────────


class ImageReader(BaseReader):
    """Đọc ảnh từ file path hoặc numpy.ndarray. Lặp đúng một lần."""

    def __init__(self, sources: list, **_):
        self._done = False
        self._frames, self._metas = self._load(sources)

    def _load(self, sources: list) -> tuple[list[np.ndarray], list[SourceMeta]]:
        """Nạp toàn bộ ảnh vào bộ nhớ ngay khi khởi tạo."""
        ts = time.time()
        frames, metas = [], []
        n = len(sources)
        for i, src in enumerate(sources):
            if isinstance(src, np.ndarray):
                frame = ensure_bgr(src)
                name = f"array_{i}"
            else:
                frame = cv2.imread(str(src))
                if frame is None:
                    LOGGER.error("Không đọc được ảnh [%d/%d]: %s", i + 1, n, src)
                    raise FileNotFoundError(f"Không đọc được ảnh: {src}")
                frame = ensure_bgr(frame)
                name = Path(src).name
            h, w = frame.shape[:2]
            LOGGER.info("Nạp ảnh [%d/%d]: %s | IMAGE | %dx%d | is_stream=False", i + 1, n, name, w, h)
            frames.append(frame)
            metas.append(SourceMeta(
                name=name,
                source_type=SourceType.IMAGE,
                frame_index=0,
                resolution=(w, h),
                timestamp=ts,
            ))
        LOGGER.info("Đã nạp %d ảnh.", n)
        return frames, metas

    def __next__(self) -> tuple[list[np.ndarray], list[SourceMeta]]:
        if self._released or self._done:
            raise StopIteration
        self._done = True
        return self._frames, self._metas

    def release(self) -> None:
        self._released = True
