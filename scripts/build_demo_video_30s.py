"""Create a continuous 30-second tour from the verified real recording."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from demo_runtime import PROJECT_DIR, configuration, read_json, write_json

CONFIG = configuration()
SOURCE_DIR = PROJECT_DIR / CONFIG["delivery_dir"]
OPTIONS = CONFIG["compact_video"]
OUTPUT = PROJECT_DIR / OPTIONS["output_dir"]
FONT = Path("C:/Windows/Fonts/msyh.ttc")
LABELS = ["选择学科并开始生成", "真实生成过程", "六个节点结果回看", "Word 预览与下载", "随机抽查与结束"]


def main():
    manifest = read_json(SOURCE_DIR / "delivery_manifest.json")
    assert manifest["video_verification"]["status"] == "pass"
    source = Path(manifest["full_webm"])
    actions = manifest["actions"]
    fps = manifest["video_metadata"]["fps"]
    source_count = manifest["video_metadata"]["frames"]
    target_count = round(OPTIONS["seconds"] * fps)
    budgets = OPTIONS["section_seconds"]
    assert len(budgets) == len(LABELS) and sum(budgets) == OPTIONS["seconds"]
    # These event boundaries only select pace regions. Every source interval is
    # traversed in order; there are no removed segments or concatenation cuts.
    finished = next(row["seconds"] for row in actions if row["action"] == "recording_finished")
    offset = finished - source_count / fps

    def event_frame(action, target=None):
        row = next(row for row in actions if row["action"] == action and (target is None or row.get("target") == target))
        return round((row["seconds"] - offset) * fps)

    boundaries = [0, event_frame("generation_started"), event_frame("generation_completed"),
                  event_frame("click", "#preview") - round(1.4 * fps),
                  event_frame("word_downloaded"), source_count]
    assert all(a < b for a, b in zip(boundaries, boundaries[1:]))
    mappings, sections, section_indices = [], [], []
    for index, (start, stop, seconds, label) in enumerate(zip(boundaries, boundaries[1:], budgets, LABELS)):
        count = round(seconds * fps)
        indices = np.rint(np.linspace(start, stop - 1, count)).astype(np.int64)
        assert np.all(np.diff(indices) > 0)
        sections.append({"label": label, "source_start": int(start), "source_stop": int(stop),
                         "output_start": len(mappings), "output_frames": count,
                         "seconds": seconds, "speed": (stop - start) / count})
        mappings.extend(indices.tolist())
        section_indices.extend([index] * count)
    mappings = np.array(mappings)
    assert len(mappings) == target_count and mappings[0] == 0 and mappings[-1] == source_count - 1
    assert np.all(np.diff(mappings) > 0)
    # Re-emphasize actual recorded clicks after acceleration, at their original
    # screen coordinates. The click timeline comes from real browser events.
    clicks = []
    for row in actions:
        if row["action"] == "click":
            source_frame = (row["seconds"] - offset) * fps
            output_frame = int(np.argmin(np.abs(mappings - source_frame)))
            clicks.append({"frame": output_frame, "x": row["x"], "y": row["y"], "target": row["target"]})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "operation-demo-30s.mp4"
    capture = cv2.VideoCapture(str(source))
    size = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    assert capture.isOpened() and size == (1600, 1000)
    writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    assert writer.isOpened()
    banners = []
    for section in sections:
        banner = Image.new("RGB", (540, 42), "#234b3b")
        draw = ImageDraw.Draw(banner)
        draw.text((15, 7), f"{section['label']} · {section['speed']:.1f} 倍速", font=ImageFont.truetype(str(FONT), 19), fill="white")
        banners.append(cv2.cvtColor(np.asarray(banner), cv2.COLOR_RGB2BGR))
    source_index, output_index = 0, 0
    snapshots = {round(seconds * fps): seconds for seconds in [2, 8, 14, 19, 24, 28]}
    gray_frames = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        band = frame[100:900, 1540:1560].astype(float)
        gray_frames += int(np.mean(np.all(np.abs(band - 128) < 5, axis=2)) > 0.95)
        if output_index < len(mappings) and source_index == mappings[output_index]:
            frame[:10, :10] = frame[12, 12]
            frame[:42, size[0] - 540:] = banners[section_indices[output_index]]
            for click in clicks:
                age = output_index - click["frame"]
                if 0 <= age < 7:
                    radius = 16 + age * 3
                    cv2.circle(frame, (click["x"], click["y"]), radius, (255, 255, 255), 5, cv2.LINE_AA)
                    cv2.circle(frame, (click["x"], click["y"]), radius, (30, 170, 235), 3, cv2.LINE_AA)
            writer.write(frame)
            if output_index in snapshots:
                cv2.imwrite(str(OUTPUT / f"frame-{snapshots[output_index]:02d}s.png"), frame)
            output_index += 1
        source_index += 1
    capture.release()
    writer.release()
    assert source_index == source_count and output_index == target_count and not gray_frames
    check = cv2.VideoCapture(str(target))
    decoded = 0
    while True:
        ok, frame = check.read()
        if not ok:
            break
        assert frame.shape[:2] == (1000, 1600)
        decoded += 1
    check.release()
    assert decoded == target_count and decoded / fps <= 30
    np.savez_compressed(OUTPUT / "video_frame_mapping.npz", source_frames=mappings)
    result = {"status": "pass", "path": str(target), "seconds": decoded / fps, "fps": fps,
              "width": size[0], "height": size[1], "source": str(source),
              "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "source_frames": source_count, "output_frames": decoded, "sections": sections,
              "clicks": clicks, "chronological_order": True, "removed_source_intervals": 0,
              "resized_gray_frames": gray_frames, "timing_basis": "continuous_section_retiming"}
    write_json(OUTPUT / "video_checks.json", result)
    (OUTPUT / "README.txt").write_text(
        "30秒学科报告操作演示\n\n选学科3秒 → 生成8秒 → 节点结果5秒 → Word预览与下载10秒 → 随机抽查4秒。\n"
        "源视频沿时间顺序连续变速，未拼接或删除中间片段。鼠标轨迹来自真实录制；点击圆环按真实点击时间和位置加强显示。\n"
        "原版及完整录屏保留在 outputs/web_demo_delivery_v2。video_checks.json 与 video_frame_mapping.npz 记录时长及帧对应关系。\n",
        encoding="utf-8", newline="\n")
    print(json.dumps({key: result[key] for key in ["status", "path", "seconds", "output_frames", "resized_gray_frames"]}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
