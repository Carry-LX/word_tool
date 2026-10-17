"""Check the cursor above dialogs and the exact frame marker before a real recording."""
from __future__ import annotations

import json
import os
from pathlib import Path

import cv2
from playwright.sync_api import sync_playwright

from demo_runtime import PROJECT_DIR, configuration, write_json

OUTPUT = PROJECT_DIR / "outputs/web_demo_validation/recording_check"


def main():
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "E:/tools/playwright"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    config = configuration()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1000}, record_video_size={"width": 1600, "height": 1000}, record_video_dir=str(OUTPUT))
        page = context.new_page()
        page.add_init_script(path=str(PROJECT_DIR / "frontend/demo/recording-cursor.js"))
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"http://{config['host']}:{config['port']}", wait_until="networkidle")
        page.wait_for_function("window.demoRecording && !document.getElementById('preview').disabled")
        page.evaluate("window.demoRecording.setIdle(true)")
        page.wait_for_timeout(900)
        page.evaluate("window.demoRecording.setIdle(false)")
        page.locator("#preview").click()
        page.wait_for_function("document.getElementById('viewer').open")
        target = page.locator("#next").bounding_box()
        x, y = target["x"] + target["width"] / 2, target["y"] + target["height"] / 2
        page.mouse.move(x, y, steps=20)
        page.mouse.down()
        page.wait_for_timeout(100)
        assert page.evaluate("document.getElementById('recording-layer').matches(':popover-open')")
        assert page.evaluate("([x,y]) => document.elementFromPoint(x,y).closest('button').id === 'next'", [x, y])
        page.screenshot(path=str(OUTPUT / "cursor-in-dialog.png"))
        page.mouse.up()
        page.wait_for_timeout(800)
        assert not errors, errors
        video = page.video
        context.close()
        path = video.path()
        browser.close()
    capture = cv2.VideoCapture(path)
    idle_frames = active_frames = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if frame[2:8, 2:8].mean() < 100:
            idle_frames += 1
        else:
            active_frames += 1
    capture.release()
    assert idle_frames > 5 and active_frames > 5
    write_json(OUTPUT / "checks.json", {"status": "pass", "cursor_above_dialog": True, "idle_frames": idle_frames, "active_frames": active_frames, "browser_errors": errors})
    print(json.dumps({"status": "pass", "idle_frames": idle_frames, "active_frames": active_frames}))


if __name__ == "__main__":
    main()
