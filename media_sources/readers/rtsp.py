import time

import cv2

from ..models import SourceMeta, SourceType
from ..utils import LOGGER, ensure_bgr, open_capture
from ._stream import _StreamReader

# ─────────────────────────────────────────────────────────────────────────────


class RtspReader(_StreamReader):
    """Đọc frame từ RTSP/RTMP streams với GStreamer/FFMPEG backend và auto-reconnect."""

    def __init__(
        self,
        sources: list[str],
        *,
        reconnect: bool = True,
        reconnect_delay: float = 2.0,
        max_reconnect_attempts: int = 5,
        reconnect_forever: bool = True,
        use_gstreamer: bool = True,
        open_timeout_ms: int = 5000,
        read_timeout_ms: int = 5000,
        **_,
    ):
        super().__init__(len(sources))
        self._sources = sources
        self._reconnect = reconnect
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_attempts = max_reconnect_attempts
        self._reconnect_forever = reconnect_forever
        self._use_gstreamer = use_gstreamer
        self._open_timeout_ms = open_timeout_ms
        self._read_timeout_ms = read_timeout_ms
        self._caps: list[cv2.VideoCapture | None] = []
        self._fps: list[float] = []

        n = len(sources)
        try:
            for i, url in enumerate(sources):
                LOGGER.info("Đang kết nối stream [%d/%d]: %s", i + 1, n, url)
                cap = self._open_cap(url)
                fps = cap.get(cv2.CAP_PROP_FPS)
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                res = f"{w}x{h}" if w > 0 and h > 0 else "unknown"

                if fps <= 0:
                    LOGGER.warning("FPS không đọc được từ stream: %s", url)
                LOGGER.info("  → RTSP | %s | %.1f fps | is_stream=True", res, fps)
                self._caps.append(cap)
                self._fps.append(fps)
        except Exception:
            for cap in self._caps:
                if cap is not None:
                    cap.release()
            raise

        self._start()

    # ─── mở kết nối ──────────────────────────────────────────────────────────

    def _open_cap(self, url: str) -> cv2.VideoCapture:
        """Thử GStreamer trước, fallback sang FFMPEG. RTMP bỏ qua GStreamer (rtspsrc không hỗ trợ rtmp)."""
        is_rtmp = url.lower().startswith("rtmp://")
        if self._use_gstreamer and not is_rtmp and self._opencv_has_gstreamer():
            cap = self._open_gstreamer(url)
            if cap is not None:
                return cap
            LOGGER.info("GStreamer không thành công, dùng FFMPEG: %s", url)
        return self._open_ffmpeg(url)

    def _open_ffmpeg(self, url: str) -> cv2.VideoCapture:
        cap = open_capture(url, cv2.CAP_FFMPEG, self._open_timeout_ms, self._read_timeout_ms)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            cap.release()
            raise RuntimeError(f"Không kết nối được stream: {url}")
        LOGGER.info("RTSP đã kết nối (FFMPEG): %s", url)
        return cap

    def _open_gstreamer(self, url: str) -> cv2.VideoCapture | None:
        """Thử lần lượt h265 → h264 và warm-up đọc 1 frame để xác nhận."""
        for codec in ("h265", "h264"):
            cap = open_capture(
                self._build_gstreamer_pipeline(url, codec), cv2.CAP_GSTREAMER,
                self._open_timeout_ms, self._read_timeout_ms,
            )
            if not cap.isOpened():
                cap.release()
                continue
            ok, frame = cap.read()
            if ok and frame is not None:
                LOGGER.info("RTSP đã kết nối (GStreamer/%s): %s", codec, url)
                return cap
            cap.release()
        return None

    def _build_gstreamer_pipeline(self, url: str, codec: str) -> str:
        url_esc = url.replace('"', '\\"')
        decode = "rtph265depay ! h265parse ! avdec_h265" if codec == "h265" else "rtph264depay ! h264parse ! avdec_h264"
        return (
            f'rtspsrc location="{url_esc}" protocols=tcp latency=200 '
            f"! queue max-size-buffers=1 leaky=downstream "
            f"! application/x-rtp,media=video "
            f"! {decode} "
            f"! videoconvert ! video/x-raw,format=BGR "
            f"! appsink sync=false drop=true max-buffers=1"
        )

    @staticmethod
    def _opencv_has_gstreamer() -> bool:
        return any(
            "GStreamer:" in line and "YES" in line
            for line in cv2.getBuildInformation().splitlines()
        )

    # ─── reader loop ─────────────────────────────────────────────────────────

    def _loop(self, i: int) -> None:
        url = self._sources[i]
        cap = self._caps[i]  # thread sở hữu cap này, tự release ở finally
        idx = 0
        attempt = 0

        try:
            while not self._stop.is_set():
                ret, frame = cap.read() if cap is not None else (False, None)

                if ret and frame is not None:
                    attempt = 0
                    frame = ensure_bgr(frame)
                    h, w = frame.shape[:2]
                    self._publish(i, frame, SourceMeta(
                        name=url,
                        source_type=SourceType.RTSP,
                        frame_index=idx,
                        resolution=(w, h),
                        fps=self._fps[i],
                        is_stream=True,
                        timestamp=time.time(),
                    ))
                    idx += 1
                    continue

                # Đọc thất bại ─────────────────────────────────────────────────
                if not self._reconnect:
                    LOGGER.warning("RTSP mất kết nối, không reconnect: %s", url)
                    self._mark_ended(i)
                    return

                attempt += 1
                if not self._reconnect_forever and attempt > self._max_reconnect_attempts:
                    LOGGER.error("RTSP bỏ cuộc sau %d lần reconnect: %s", self._max_reconnect_attempts, url)
                    self._mark_ended(i)
                    return

                LOGGER.warning("RTSP mất kết nối, thử lại lần %d: %s", attempt, url)
                if cap is not None:
                    cap.release()
                    cap = None

                if self._stop.wait(timeout=self._reconnect_delay):
                    return

                try:
                    cap = self._open_cap(url)
                    LOGGER.info("RTSP reconnect thành công (lần %d): %s", attempt, url)
                except Exception as exc:
                    LOGGER.warning("RTSP reconnect lần %d thất bại: %s", attempt, exc)
                    cap = None
        finally:
            if cap is not None:
                cap.release()

    def release(self) -> None:
        # Chỉ dừng + join threads; mỗi thread tự release cap của mình (tránh race release-trong-khi-read)
        super().release()
