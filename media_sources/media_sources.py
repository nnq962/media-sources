import numpy as np

from .detector import detect_source_type
from .models import SourceMeta, SourceType
from .readers.base import BaseReader
from .readers.image import ImageReader
from .readers.rtsp import RtspReader
from .readers.video import VideoReader
from .readers.webcam import WebcamReader
from .readers.youtube import YoutubeReader

# ─────────────────────────────────────────────────────────────────────────────

_READER_MAP: dict[SourceType, type[BaseReader]] = {
    SourceType.IMAGE: ImageReader,
    SourceType.VIDEO: VideoReader,
    SourceType.WEBCAM: WebcamReader,
    SourceType.RTSP: RtspReader,
    SourceType.YOUTUBE: YoutubeReader,
}

# ─────────────────────────────────────────────────────────────────────────────


class MediaSources:
    """Interface thống nhất để đọc frame từ nhiều nguồn media cùng loại."""

    def __init__(self, sources: list, **kwargs):
        """
        kwargs cho RtspReader: reconnect, reconnect_delay, max_reconnect_attempts,
          reconnect_forever, use_gstreamer, open_timeout_ms, read_timeout_ms.
        kwargs cho YoutubeReader: không có thêm (kế thừa VideoReader).
        """
        source_type = detect_source_type(sources)
        self._reader = _READER_MAP[source_type](sources, **kwargs)

    def __iter__(self):
        return self

    def __next__(self) -> tuple[list[np.ndarray], list[SourceMeta]]:
        return next(self._reader)

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self._reader.release()

    def release(self) -> None:
        """Giải phóng tất cả tài nguyên."""
        self._reader.release()
