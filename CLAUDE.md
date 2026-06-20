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

Kiến trúc tách **reader đơn nguồn** (1 reader = 1 source, vòng đời `open/read/close`) khỏi **batch
orchestrator** (gói N reader). `create_media_source()` (factory) là điểm vào; `MediaSources` là wrapper
batch tiện dụng (giữ tương thích cũ). Luồng dữ liệu:

```
create_media_source(source | list, **kwargs)        # KHÔNG kết nối — lazy
    ├─ source đơn  → _classify_one() → Reader(source)            # open/read/close độc lập
    └─ list        → detect_source_type()  # classify MỌI item, raise nếu trộn loại
                     → [Reader(src) for src in list]  (kwargs lọc qua _reader_kwargs)
                     → StreamBatchReader  (reader.is_stream=True: rtsp/webcam)
                     └─ SyncBatchReader   (còn lại: image/video/youtube)

MediaSources(sources, **kwargs) → create_media_source(...) ; __next__ → (frames, metas)
```

**Lazy open:** construct KHÔNG kết nối; chỉ mở khi `open()` / vào `with` / lần `__next__` đầu. `ensure_open()`
idempotent. `read()` trả `(frame, meta)` hoặc `None` (hết nguồn/mất tín hiệu).

**Batch luôn đồng nhất** — mọi source trong batch phải cùng loại; `detect_source_type` validate và báo
lỗi rõ nếu trộn (vd `["a.mp4", "b.jpg"]`). (Mixed type là chủ ý KHÔNG hỗ trợ.)

**Hai chiến lược batch** (chọn theo class attr `is_stream` của reader — batch đồng nhất nên toàn-stream
hoặc toàn-file):
- **`SyncBatchReader`** (image/video/youtube, `is_stream=False`): lockstep — mỗi vòng đọc 1 frame từ MỌI
  reader song song bằng `ThreadPoolExecutor`, **KHÔNG drop frame**. Bất kỳ reader hết nguồn → `StopIteration`.
- **`StreamBatchReader`** (rtsp/webcam, `is_stream=True`): mỗi reader một daemon thread đọc liên tục vào
  slot; `__next__` chỉ trả batch khi **tất cả** slot có frame mới (đồng bộ theo index, luôn lấy frame mới
  nhất — drop frame cũ để giữ realtime). Hết nguồn → `StopIteration`; lỗi trong thread → `StreamError`.

**Vòng đời theo loại:**
- `ImageReader`: `read()` trả 1 lần rồi `None` (ảnh static).
- `VideoReader` / `YoutubeReader`: đọc đến hết file rồi `None`.
- `WebcamReader` / `RtspReader`: stream vô hạn. RTSP **reconnect nằm trong `read()`** (exponential backoff,
  reset attempt khi thành công, `reconnect_forever` mặc định), auto-detect codec h264→h265, open/read timeout.

**Quản lý tài nguyên:** trong `StreamBatchReader`, mỗi thread tự `reader.close()` (release `VideoCapture`)
ở `finally`; lúc đóng, batch set stop-event + gọi `reader.request_stop()` (báo RTSP thoát vòng reconnect mà
KHÔNG release cap từ thread khác — tránh race) rồi join thread.

**Cấu trúc package:**
```
media_sources/
├── __init__.py          # export MediaSources, create_media_source, BaseReader, Stream/SyncBatchReader, ...
├── media_sources.py     # class MediaSources (wrapper batch mỏng, lazy)
├── factory.py           # create_media_source() + _READER_MAP + _reader_kwargs() (lọc kwargs theo signature)
├── batch.py             # _BaseBatch, SyncBatchReader (lockstep), StreamBatchReader (daemon-thread latest-frame)
├── detector.py          # detect_source_type() + _classify_one()
├── models.py            # SourceType (enum), SourceMeta (dataclass)
├── exceptions.py        # MediaSourceError, StreamError
├── utils.py             # LOGGER, set_logging(), ensure_bgr(), open_capture()
└── readers/
    ├── base.py          # BaseReader (ABC) — đơn nguồn, open/read/close, lazy, request_stop()
    ├── image.py         # path + numpy.ndarray, read() 1 lần
    ├── video.py         # file video (hook _capture_target cho youtube)
    ├── webcam.py        # device id (int)
    ├── rtsp.py          # rtsp:// / rtmp://, GStreamer→FFMPEG, reconnect trong read()
    └── youtube.py       # YouTube URL qua yt-dlp (kế thừa VideoReader)
```

**Thêm reader mới:** tạo file trong `readers/` kế thừa `BaseReader` (đặt `source_type` + `is_stream`,
hiện thực `open/read/close`), đăng ký vào `_READER_MAP` (`factory.py`), thêm nhánh trong `_classify_one()`
(`detector.py`). Batch strategy tự chọn theo `is_stream`.

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
