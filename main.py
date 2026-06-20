from media_sources import MediaSources
from media_sources.utils import set_logging

import cv2
import numpy as np


def main() -> None:
    set_logging()

    sources = ["rtsp://admin:061223%40bC@192.168.0.10:554/Streaming/Channels/101", "rtsp://admin:061223%40bC@192.168.0.15:554/Streaming/Channels/101"] * 3

    # sources = [
    # "https://youtu.be/vCIc1g_4JWM?si=Bpb2kriUjQwaGQen",
    # "https://youtu.be/vCIc1g_4JWM?si=Bpb2kriUjQwaGQen",
    # ]

    # sources = ["examples/crowd.mp4"] * 5

    target_h = 480

    with MediaSources(sources, use_gstreamer=True) as ms:
        for frames, infos in ms:
            resized_frames = resize_frames_to_height(frames, target_h)
            draw_frame_labels(resized_frames, infos)

            combined = np.hstack(resized_frames)
            print(f"combined shape: {combined.shape}")


def resize_frames_to_height(frames: list[np.ndarray], target_h: int) -> list[np.ndarray]:
    resized_frames = []

    for frame in frames:
        h, w = frame.shape[:2]
        new_w = int(w * target_h / h)
        resized_frame = cv2.resize(frame, (new_w, target_h))
        resized_frames.append(resized_frame)

    return resized_frames


def draw_frame_labels(frames: list[np.ndarray], infos) -> None:
    for i, (frame, info) in enumerate(zip(frames, infos)):
        label = f"[{i}] {info.source_type.name} {info.resolution[0]}x{info.resolution[1]}"

        cv2.putText(
            frame,
            label,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )


if __name__ == "__main__":
    main()