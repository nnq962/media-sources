from __future__ import annotations

from dataclasses import replace

import yt_dlp

from ..models import SourceMeta, SourceType
from ..utils import LOGGER
from .video import VideoReader

# ─────────────────────────────────────────────────────────────────────────────


class YoutubeReader(VideoReader):
    """Đọc frame từ YouTube URL: dùng yt-dlp lấy direct stream URL rồi đọc qua VideoReader."""

    def __init__(self, sources: list[str], **kwargs):
        self._youtube_urls = sources
        self._is_live: list[bool] = []
        self._yt_fps: list[float | None] = []
        resolved = self._resolve_all(sources)
        super().__init__(resolved, **kwargs)

    # ─── resolve ─────────────────────────────────────────────────────────────

    def _resolve_all(self, urls: list[str]) -> list[str]:
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "quiet": True,
            "no_warnings": True,
        }
        resolved = []
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for i, url in enumerate(urls):
                LOGGER.info("Đang lấy stream URL [%d/%d]: %s", i + 1, len(urls), url)
                try:
                    info = ydl.extract_info(url, download=False)
                    stream_url = info["url"]
                    is_live = bool(info.get("is_live"))
                    fps = info.get("fps")
                    w = info.get("width") or 0
                    h = info.get("height") or 0
                    LOGGER.info("  → YOUTUBE | %dx%d | %.0f fps | is_stream=%s | %s",
                                w, h, fps or 0, is_live,
                                info.get("title") or "(no title)")
                    resolved.append(stream_url)
                    self._is_live.append(is_live)
                    self._yt_fps.append(fps)
                except Exception as exc:
                    LOGGER.error("Không lấy được stream URL: %s — %s", url, exc)
                    raise RuntimeError(f"Không lấy được stream URL: {url}") from exc
        return resolved

    # ─── patch metadata ───────────────────────────────────────────────────────

    def __next__(self) -> tuple[list, list[SourceMeta]]:
        frames, metas = super().__next__()
        patched = []
        for i, meta in enumerate(metas):
            is_live = self._is_live[i]
            patched.append(replace(
                meta,
                name=self._youtube_urls[i],
                source_type=SourceType.YOUTUBE,
                is_stream=is_live,
                # live stream không có tổng số frame xác định
                total_frames=None if is_live else meta.total_frames,
                # cap đôi khi đọc fps=0, fallback theo metadata yt-dlp
                fps=meta.fps if meta.fps and meta.fps > 0 else self._yt_fps[i],
            ))
        return frames, patched
