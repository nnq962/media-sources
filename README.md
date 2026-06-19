# media-sources

`media-sources` chuẩn hóa cách đọc dữ liệu từ nhiều nguồn media khác nhau và trả ra frame theo từng
vòng lặp, để phần xử lý AI phía sau (YOLO, RetinaFace, các pipeline ảnh/video…) làm việc với một giao
diện thống nhất. Đầu vào luôn được xử lý theo **batch** và trả frame kèm metadata theo đúng thứ tự nguồn.

## Nguồn đầu vào hỗ trợ

| Loại | Ví dụ | Ghi chú |
|---|---|---|
| Ảnh (path) | `"img.jpg"` | lặp 1 lần |
| Ảnh (`numpy.ndarray`) | `frame` | tự chuẩn hóa về BGR 3-channel |
| Video (path) | `"clip.mp4"` | lặp đến hết file |
| Webcam | `0`, `1` | stream vô hạn |
| RTSP / RTMP | `"rtsp://..."` | stream vô hạn, auto-reconnect |
| YouTube | `"https://youtu.be/..."` | resolve qua `yt-dlp` |

> **Batch luôn đồng nhất:** mọi phần tử trong một batch phải cùng loại. Trộn loại
> (vd `["a.mp4", "b.jpg"]`) sẽ raise `ValueError` ngay khi khởi tạo.

## Cài đặt

```bash
uv sync
```

## Bắt đầu nhanh

```python
from media_sources import MediaSources
from media_sources.utils import set_logging

set_logging()  # (tuỳ chọn) bật log màu mức INFO

sources = ["rtsp://cam1", "rtsp://cam2"]

with MediaSources(sources) as ms:
    for frames, infos in ms:
        # frames[0] là frame hiện tại của cam1, frames[1] của cam2
        # infos[i] là metadata tương ứng với frames[i]
        results = model.predict(frames)
```

Mỗi vòng lặp trả về `(frames, infos)`:
- `frames`: `list[numpy.ndarray]` (BGR 3-channel), đúng thứ tự nguồn đầu vào.
- `infos`: `list[SourceMeta]` tương ứng theo index — `frames[i]` ↔ `infos[i]` ↔ `sources[i]`.

## Ví dụ theo từng loại nguồn

```python
import numpy as np
from media_sources import MediaSources

# Ảnh path
MediaSources(["a.jpg", "b.png"])

# numpy.ndarray (grayscale/BGRA tự chuẩn hóa về BGR)
MediaSources([np.zeros((480, 640, 3), np.uint8)])

# Video
MediaSources(["video1.mp4", "video2.mp4"])

# Webcam
MediaSources([0, 1])

# RTSP (tắt GStreamer, chỉ dùng FFMPEG)
MediaSources(["rtsp://cam1"], use_gstreamer=False)

# YouTube
MediaSources(["https://youtu.be/vCIc1g_4JWM"])
```

## Metadata — `SourceMeta`

| Field | Kiểu | Ý nghĩa |
|---|---|---|
| `name` | `str` | tên file / `"webcam_0"` / URL |
| `source_type` | `SourceType` | `IMAGE` `VIDEO` `WEBCAM` `RTSP` `YOUTUBE` |
| `frame_index` | `int` | chỉ số frame hiện tại của nguồn |
| `resolution` | `tuple[int, int]` | `(width, height)` |
| `fps` | `float \| None` | `None` với ảnh |
| `total_frames` | `int \| None` | chỉ có với video (file) |
| `is_stream` | `bool` | `True` với webcam/RTSP/YouTube-live |
| `timestamp` | `float` | thời điểm đọc frame (epoch giây) |

```python
from media_sources import SourceType

for frames, infos in ms:
    if infos[0].source_type == SourceType.RTSP:
        ...
```

## Tuỳ chọn RTSP

Truyền qua `**kwargs` của `MediaSources` (chỉ áp dụng cho nguồn RTSP):

| kwarg | Mặc định | Ý nghĩa |
|---|---|---|
| `use_gstreamer` | `True` | thử GStreamer (low-latency) trước, fallback FFMPEG |
| `reconnect` | `True` | tự kết nối lại khi mất tín hiệu |
| `reconnect_delay` | `2.0` | giây chờ giữa các lần reconnect |
| `reconnect_forever` | `True` | reconnect vô hạn (bỏ qua `max_reconnect_attempts`) |
| `max_reconnect_attempts` | `5` | số lần thử khi `reconnect_forever=False` |
| `open_timeout_ms` | `5000` | timeout mở kết nối (chống treo) |
| `read_timeout_ms` | `5000` | timeout đọc frame (chống treo) |

```python
MediaSources(
    ["rtsp://cam1", "rtsp://cam2"],
    reconnect_forever=True,
    reconnect_delay=2.0,
    use_gstreamer=True,
)
```

## Xử lý lỗi

Stream (webcam/RTSP) gặp lỗi khi đọc sẽ raise `StreamError` — phân biệt rõ với kết thúc bình thường
(`StopIteration`):

```python
from media_sources import MediaSources, StreamError
from media_sources.utils import LOGGER

try:
    with MediaSources(["rtsp://cam1"]) as ms:
        for frames, infos in ms:
            model.predict(frames)
except StreamError as e:
    LOGGER.error("Stream chết: %s", e)
    # restart / cảnh báo / ...
```

## Logging

Library **không** tự cấu hình logging khi import (chỉ gắn `NullHandler`). Muốn log màu, gọi
`set_logging()` (mặc định INFO) ở phía ứng dụng:

```python
from media_sources.utils import set_logging
set_logging()            # INFO
set_logging(debug=True)  # DEBUG
```

## Định hướng thiết kế

- Interface thống nhất cho ảnh, video, webcam, RTSP, YouTube; batch ngay từ đầu.
- Giữ đúng thứ tự đầu vào trong cả `frames` và `infos`.
- Bền cho pipeline chạy 24/7: timeout chống treo, auto-reconnect RTSP, dừng thread sạch.
- Dễ mở rộng nguồn mới (thêm reader + đăng ký).
