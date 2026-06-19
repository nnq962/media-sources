import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from ..models import SourceMeta, SourceType
from ..utils import LOGGER, ensure_bgr
from .base import BaseReader

# ─────────────────────────────────────────────────────────────────────────────


class VideoReader(BaseReader):
    """Đọc frame từng bước từ một batch video file, các file decode song song."""

    def __init__(self, sources: list, **_):
        self._sources = [str(s) for s in sources]
        self._frame_indices = [0] * len(sources)
        self._caps: list[cv2.VideoCapture] = []
        self._fps: list[float] = []
        self._total_frames: list[int] = []
        self._executor: ThreadPoolExecutor | None = None

        n = len(sources)
        try:
            for i, src in enumerate(self._sources):
                LOGGER.info("Mở video [%d/%d]: %s", i + 1, n, src)
                cap = cv2.VideoCapture(src)
                if not cap.isOpened():
                    cap.release()
                    LOGGER.error("Không mở được video: %s", src)
                    raise FileNotFoundError(f"Không mở được video: {src}")

                fps = cap.get(cv2.CAP_PROP_FPS)
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

                if fps <= 0:
                    LOGGER.warning("FPS không đọc được từ video: %s", src)
                if total <= 0:
                    LOGGER.warning("Số frame không đọc được từ video: %s", src)
                LOGGER.info("  → VIDEO | %dx%d | %.1f fps | %d frames | is_stream=False", w, h, fps, total)

                self._caps.append(cap)
                self._fps.append(fps)
                self._total_frames.append(total)

            self._executor = ThreadPoolExecutor(max_workers=n)
        except Exception:
            for cap in self._caps:
                cap.release()
            raise

    def __next__(self) -> tuple[list[np.ndarray], list[SourceMeta]]:
        if self._released:
            raise StopIteration
        ts = time.time()
        results = list(self._executor.map(lambda cap: cap.read(), self._caps))
        frames, metas = [], []
        for i, (ret, frame) in enumerate(results):
            if not ret:
                LOGGER.info("Video kết thúc: %s", self._sources[i])
                self.release()
                raise StopIteration
            frame = ensure_bgr(frame)
            h, w = frame.shape[:2]
            frames.append(frame)
            metas.append(SourceMeta(
                name=Path(self._sources[i]).name,
                source_type=SourceType.VIDEO,
                frame_index=self._frame_indices[i],
                resolution=(w, h),
                fps=self._fps[i],
                total_frames=self._total_frames[i],
                timestamp=ts,
            ))
            self._frame_indices[i] += 1
        return frames, metas

    def release(self) -> None:
        self._released = True
        if self._executor is not None:
            self._executor.shutdown(wait=False)
        for cap in self._caps:
            cap.release()
        self._caps = []
