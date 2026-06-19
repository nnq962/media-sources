from abc import ABC, abstractmethod

import numpy as np

from ..models import SourceMeta

# ─────────────────────────────────────────────────────────────────────────────


class BaseReader(ABC):
    """Abstract base class cho tất cả reader."""

    # release() set True; __next__ phải raise StopIteration sau khi đã release.
    _released = False

    def __iter__(self):
        return self

    @abstractmethod
    def __next__(self) -> tuple[list[np.ndarray], list[SourceMeta]]:
        ...

    def read(self) -> tuple[list[np.ndarray], list[SourceMeta]]:
        """Đọc một batch frame từ tất cả sources."""
        return self.__next__()

    @abstractmethod
    def release(self) -> None:
        """Giải phóng tài nguyên."""
        ...
