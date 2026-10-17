"""Audit continuous retiming against the actual source recording."""
from __future__ import annotations

import json

import cv2
import numpy as np

from demo_runtime import PROJECT_DIR, configuration, read_json, write_json

OUTPUT = PROJECT_DIR / configuration()["delivery_dir"]


def main():
    manifest = read_json(OUTPUT / "delivery_manifest.json")
    short = manifest["short_video"]
    data = np.load(OUTPUT / "video_frame_mapping.npz")
    indices, idle = data["source_frames"], data["idle_flags"]
    assert np.all(np.diff(indices) > 0)
    kept = np.zeros(len(idle), dtype=bool)
    kept[indices] = True
    assert np.all(kept[~idle])
    capture = cv2.VideoCapture(short["path"])
    fps, decoded = capture.get(cv2.CAP_PROP_FPS), 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        assert frame.shape[:2] == (1000, 1600)
        decoded += 1
    capture.release()
    assert decoded == short["output_frames"] and fps == 25
    actions = manifest["actions"]
    assert {row["stage"] for row in actions if row["action"] == "node_result_reviewed"} == {row["id"] for row in configuration()["stages"]}
    assert sum(row["action"] == "click" for row in actions) >= 15
    # During the six node reviews there is no intentional page scroll. A full-page
    # screenshot must not cause the video viewport/header to resize or flash.
    end = next(row["seconds"] for row in actions if row["action"] == "recording_finished")
    offset = end - manifest["video_metadata"]["seconds"]
    start = next(row["seconds"] for row in actions if row["action"] == "generation_completed") - offset
    stop = next(row["seconds"] for row in actions if row["action"] == "node_result_reviewed" and row["stage"] == "qa") - offset
    source = cv2.VideoCapture(manifest["full_webm"])
    reference = None
    differences, gray_frames = [], []
    captured_flash, source_index = False, 0
    while True:
        ok, frame = source.read()
        if not ok:
            break
        band = frame[100:900, 1540:1560]
        if np.mean(np.all(np.abs(band.astype(float) - 128) < 5, axis=2)) > 0.95:
            gray_frames.append(source_index)
        at = source_index / fps
        source_index += 1
        if start + 0.5 <= at <= stop:
            if reference is None:
                cv2.imwrite(str(OUTPUT / "video-header-reference.png"), frame)
                reference = frame[12:85, 110:400].copy()
            difference = float(cv2.absdiff(frame[12:85, 110:400], reference).mean())
            differences.append(difference)
            if difference > 8 and not captured_flash:
                cv2.imwrite(str(OUTPUT / "video-header-difference.png"), frame)
                captured_flash = True
    source.release()
    assert differences and max(differences) < 8, f"Viewport flash during node review: {max(differences)}"
    assert not gray_frames, f"Resized screencast frames with gray borders: {gray_frames[:10]}"
    result = {"status": "pass", "decoded_frames": decoded, "seconds": decoded / fps,
              "all_active_frames_kept": True, "source_order_monotonic": True,
              "header_max_pixel_difference": max(differences), "resized_gray_frames": len(gray_frames), "six_node_reviews": True,
              "cursor_dialog_check": read_json(PROJECT_DIR / "outputs/web_demo_validation/recording_check/checks.json")["status"]}
    write_json(OUTPUT / "video_continuity_check.json", result)
    print(json.dumps(result), flush=True)
    return result


if __name__ == "__main__":
    main()
