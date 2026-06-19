# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`media-sources` là module Python 3.10+ (quản lý bằng [uv](https://github.com/astral-sh/uv)) cung cấp
một interface thống nhất để load nhiều loại media đầu vào theo dạng batch cho các pipeline AI
(YOLO, RetinaFace, …). Đầu vào được trừu tượng hóa sau iterator `MediaSources`, mỗi vòng lặp trả ra
`(frames, metas)`.

Dependencies: `opencv-python`, `numpy`, `colorlog`, `pytz`, `yt-dlp`.

## Commands

```bash
uv sync                      # cài/đồng bộ môi trường
uv run python main.py        # chạy demo
uv add <package>             # thêm dependency
uv run <command>             # chạy lệnh trong venv
```

Chưa cấu hình test/linter/formatter. Khi thêm, ưu tiên `pytest` + `ruff`.

## Architecture

`MediaSources` là iterator duy nhất người dùng tương tác. Luồng dữ liệu:

```
MediaSources(sources, **kwargs)
    → detect_source_type()   # classify MỌI item, raise ValueError nếu batch trộn loại
    → _READER_MAP[type]      # chọn reader, truyền **kwargs
    → reader.__next__()      # trả (frames, metas) mỗi vòng lặp
```

**Batch luôn đồng nhất** — mọi source trong batch phải cùng loại; `detect_source_type` validate điều
này và báo lỗi rõ nếu trộn (vd `["a.mp4", "b.jpg"]`).

**Hai họ reader:**
- **Đọc đồng bộ** (`BaseReader`): `ImageReader`, `VideoReader`. `__next__` đọc trực tiếp; VideoReader
  decode các file song song bằng `ThreadPoolExecutor`.
- **Stream nền** (`_StreamReader`): `WebcamReader`, `RtspReader`. Mỗi source một daemon thread đọc
  liên tục vào slot; `__next__` chỉ trả batch khi **tất cả** slot có frame mới (đồng bộ theo index,
  luôn lấy frame mới nhất). `YoutubeReader` kế thừa `VideoReader` (resolve URL qua yt-dlp rồi đọc như video).

**Vòng đời iterator theo loại:**
- `ImageReader`: lặp đúng **một lần** (ảnh là static).
- `VideoReader` / `YoutubeReader`: lặp đến hết file, rồi `StopIteration`.
- `WebcamReader` / `RtspReader`: lặp vô hạn. Kết thúc thật (mất tín hiệu) → `StopIteration`; lỗi trong
  thread → raise `StreamError` (không giấu thành `StopIteration`). RTSP có auto-reconnect + open/read timeout.

**Quản lý tài nguyên:** mỗi stream thread tự `release()` `VideoCapture` của nó trong `finally`;
`release()` ở reader chỉ stop + join thread (tránh race release-trong-khi-`read()`).

**Cấu trúc package:**
```
media_sources/
├── __init__.py          # export MediaSources, SourceType, SourceMeta, StreamError, MediaSourceError
├── media_sources.py     # class MediaSources + _READER_MAP
├── detector.py          # detect_source_type() + _classify_one()
├── models.py            # SourceType (enum), SourceMeta (dataclass)
├── exceptions.py        # MediaSourceError, StreamError
├── utils.py             # LOGGER, set_logging(), ensure_bgr()
└── readers/
    ├── base.py          # BaseReader (ABC)
    ├── _stream.py       # _StreamReader (daemon-thread base cho webcam/rtsp)
    ├── image.py         # path + numpy.ndarray, lặp 1 lần
    ├── video.py         # file video, decode song song
    ├── webcam.py        # device id (int)
    ├── rtsp.py          # rtsp:// / rtmp://, GStreamer→FFMPEG fallback, reconnect
    └── youtube.py       # YouTube URL qua yt-dlp
```

**Thêm reader mới:** tạo file trong `readers/` (kế thừa `BaseReader` hoặc `_StreamReader`), đăng ký
vào `_READER_MAP` (`media_sources.py`), thêm nhánh trong `_classify_one()` (`detector.py`).

## Conventions

- Mọi frame trả ra phải là BGR 3-channel — đi qua `ensure_bgr()` (utils.py) để chuẩn hóa grayscale/BGRA
  và reject shape/channel không hợp lệ.
- Tách top-level class/function bằng dòng comment:

```python
# ─────────────────────────────────────────────────────────────────────────────
```

- Docstring và comment viết bằng tiếng Việt.
- Dùng logger chung, không tạo logger lẻ: `from ..utils import LOGGER` (trong package) hoặc
  `from media_sources.utils import LOGGER` (ngoài package).
- Library **không** tự cấu hình logging khi import (chỉ gắn `NullHandler`). App muốn log màu thì gọi
  `set_logging()` (mặc định level INFO) — xem `main.py`.
