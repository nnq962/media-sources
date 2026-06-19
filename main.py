from media_sources import MediaSources
from media_sources.utils import set_logging

import cv2
import numpy as np


def main() -> None:
    set_logging()  # bật log màu (INFO); library không tự cấu hình logging khi import

    # sources = ["rtsp://admin:0612232026camera@192.168.2.50:554/Streaming/Channels/101"] * 2

    # sources = [
    #     "https://youtu.be/vCIc1g_4JWM",
    #     "https://youtu.be/vCIc1g_4JWM",
    # ]

    # sources = ["examples/crowd.mp4", "examples/ScreenRecording_04-17-2026 4-31-45 PM_1.MP4"] * 2
    # sources = ["examples/IMG_0514.JPEG"] * 10
    sources = [0, 0]

    target_h = 480

    with MediaSources(sources, use_gstreamer=False) as ms:
        for frames, infos in ms:
            resized_frames = resize_frames_to_height(frames, target_h)
            draw_frame_labels(resized_frames, infos)

            combined = np.hstack(resized_frames)
            cv2.imshow("Batch Preview", combined)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cv2.destroyAllWindows()


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