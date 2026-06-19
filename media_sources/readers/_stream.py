from __future__ import annotations

import threading
from abc import abstractmethod

import numpy as np

from ..exceptions import StreamError
from ..models import SourceMeta
from ..utils import LOGGER
from .base import BaseReader

# ─────────────────────────────────────────────────────────────────────────────


class _StreamReader(BaseReader):
    """Base cho stream readers: mỗi source một daemon thread, trả frame mới nhất."""

    def __init__(self, n: int):
        self._n = n
        self._lock = threading.Condition()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._slots: list[tuple[np.ndarray, SourceMeta] | None] = [None] * n
        self._versions: list[int] = [0] * n
        self._last_seen: list[int] = [0] * n
        self._ended: list[bool] = [False] * n
        self._errors: list[BaseException | None] = [None] * n

    def _start(self) -> None:
        """Khởi động một daemon thread cho mỗi source."""
        for i in range(self._n):
            t = threading.Thread(
                target=self._safe_loop,
                args=(i,),
                daemon=True,
                name=f"stream-reader-{i}",
            )
            t.start()
            self._threads.append(t)

    def _safe_loop(self, i: int) -> None:
        try:
            self._loop(i)
        except Exception as exc:
            LOGGER.error("Lỗi không xử lý được ở stream %d: %s", i, exc)
            self._mark_error(i, exc)

    @abstractmethod
    def _loop(self, i: int) -> None:
        """Đọc frame liên tục, gọi _publish() mỗi frame hoặc _mark_ended() khi xong."""
        ...

    def _publish(self, i: int, frame: np.ndarray, meta: SourceMeta) -> None:
        """Ghi frame mới vào slot i và thông báo cho __next__."""
        with self._lock:
            self._slots[i] = (frame, meta)
            self._versions[i] += 1
            self._lock.notify_all()

    def _mark_ended(self, i: int) -> None:
        with self._lock:
            self._ended[i] = True
            self._lock.notify_all()

    def _mark_error(self, i: int, exc: BaseException) -> None:
        with self._lock:
            self._errors[i] = exc
            self._lock.notify_all()

    def __next__(self) -> tuple[list[np.ndarray], list[SourceMeta]]:
        with self._lock:
            while True:
                if self._stop.is_set():
                    raise StopIteration

                # Stream lỗi → propagate cho consumer (không giấu thành StopIteration)
                for i, err in enumerate(self._errors):
                    if err is not None:
                        raise StreamError(f"Stream {i} gặp lỗi khi đọc frame: {err}") from err

                # Source đã kết thúc bình thường và không còn frame mới để yield
                for i in range(self._n):
                    if self._ended[i] and self._versions[i] <= self._last_seen[i]:
                        raise StopIteration

                # Tất cả slots đều có frame mới hơn lần trả trước
                if all(self._versions[i] > self._last_seen[i] for i in range(self._n)):
                    frames = [self._slots[i][0] for i in range(self._n)]
                    metas = [self._slots[i][1] for i in range(self._n)]
                    self._last_seen = list(self._versions)
                    return frames, metas

                self._lock.wait(timeout=0.1)

    def release(self) -> None:
        self._released = True
        self._stop.set()
        with self._lock:
            self._lock.notify_all()
        for t in self._threads:
            t.join(timeout=2.0)
            if t.is_alive():
                LOGGER.warning("Thread không dừng đúng hạn: %s", t.name)
        self._threads = []
