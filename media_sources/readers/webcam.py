import time

import cv2

from ..models import SourceMeta, SourceType
from ..utils import LOGGER, ensure_bgr
from ._stream import _StreamReader

# ─────────────────────────────────────────────────────────────────────────────


class WebcamReader(_StreamReader):
    """Đọc frame liên tục từ một hoặc nhiều webcam, mỗi cam một thread riêng."""

    def __init__(self, sources: list[int], **_):
        super().__init__(len(sources))
        self._sources = sources
        self._caps: list[cv2.VideoCapture] = []
        self._fps: list[float] = []

        n = len(sources)
        try:
            for i, device_id in enumerate(sources):
                LOGGER.info("Mở webcam [%d/%d]: device %d", i + 1, n, device_id)
                # KHÔNG truyền open/read timeout: backend webcam (AVFOUNDATION/V4L2/DSHOW)
                # có thể từ chối param và fail mở camera. Timeout chỉ dùng cho RTSP/FFMPEG.
                cap = cv2.VideoCapture(device_id)
                if not cap.isOpened():
                    cap.release()
                    LOGGER.error("Không mở được webcam %d.", device_id)
                    raise RuntimeError(f"Không mở được webcam {device_id}.")

                fps = cap.get(cv2.CAP_PROP_FPS)
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

                if fps <= 0:
                    LOGGER.warning("FPS không đọc được từ webcam %d.", device_id)
                LOGGER.info("  → WEBCAM | %dx%d | %.1f fps | is_stream=True", w, h, fps)

                self._caps.append(cap)
                self._fps.append(fps)
        except Exception:
            for cap in self._caps:
                cap.release()
            raise

        self._start()

    def _loop(self, i: int) -> None:
        cap = self._caps[i]  # thread sở hữu cap này, tự release ở finally
        idx = 0
        try:
            while not self._stop.is_set():
                ret, frame = cap.read()
                if not ret or frame is None:
                    LOGGER.warning("Webcam %d mất tín hiệu.", self._sources[i])
                    self._mark_ended(i)
                    return
                frame = ensure_bgr(frame)
                h, w = frame.shape[:2]
                self._publish(i, frame, SourceMeta(
                    name=f"webcam_{self._sources[i]}",
                    source_type=SourceType.WEBCAM,
                    frame_index=idx,
                    resolution=(w, h),
                    fps=self._fps[i],
                    is_stream=True,
                    timestamp=time.time(),
                ))
                idx += 1
        finally:
            cap.release()

    def release(self) -> None:
        # Best-effort: dừng + join threads; mỗi thread tự release cap trong finally. Webcam không
        # có read timeout (backend không hỗ trợ), nên nếu cap.read() block thì thread (daemon) có thể sống tiếp.
        super().release()
