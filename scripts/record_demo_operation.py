"""Continuously record real generation, readable node results, and visible clicks."""
from __future__ import annotations
import hashlib
import json
import os
import time
from pathlib import Path
import cv2
from playwright.sync_api import sync_playwright
from demo_runtime import PROJECT_DIR, configuration, now, write_json

SUBJECT_CODE = "0830"
OUTPUT_DIR = PROJECT_DIR / configuration()["delivery_dir"]
RECORD_SIZE = {"width": 1600, "height": 1000}
MAX_RUN_SECONDS = 1200
PLAYWRIGHT_TOOLS = Path("E:/tools/playwright")


def convert_video(source: Path, target: Path) -> dict:
    capture = cv2.VideoCapture(str(source))
    fps = capture.get(cv2.CAP_PROP_FPS)
    size = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    if not capture.isOpened() or not fps or not all(size):
        raise RuntimeError("Cannot decode operation recording")
    output = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"mp4v"), fps, size)
    if not output.isOpened():
        raise RuntimeError("Cannot create MP4 recording")
    frames = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        frame[:10, :10] = frame[12, 12]
        output.write(frame)
        frames += 1
    capture.release()
    output.release()
    if not frames:
        raise RuntimeError("The recording contains no decoded frames")
    return {"fps": fps, "frames": frames, "width": size[0], "height": size[1], "seconds": frames / fps}


def main():
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(PLAYWRIGHT_TOOLS)
    config = configuration()
    base_url = f"http://{config['host']}:{config['port']}"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if (OUTPUT_DIR / "operation-full.webm").exists():
        raise FileExistsError("This directory already contains a completed recording")
    request_path = PROJECT_DIR / "configs/runtime/current_subject_request.json"
    request_hash = hashlib.sha256(request_path.read_bytes()).hexdigest()
    started = time.monotonic()
    actions, errors, observed = [], [], set()

    def record(action: str, **fields):
        event = {"action": action, "seconds": round(time.monotonic() - started, 2), "at": now(), **fields}
        actions.append(event)
        write_json(OUTPUT_DIR / "operation_timeline.json", actions)
        print(json.dumps(event, ensure_ascii=True), flush=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport=RECORD_SIZE, device_scale_factor=1, record_video_dir=str(OUTPUT_DIR / "recordings"), record_video_size=RECORD_SIZE, accept_downloads=True)
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script(path=str(PROJECT_DIR / "frontend/demo/recording-cursor.js"))
        pointer = [800.0, 180.0]

        def idle(value):
            page.evaluate("value => window.demoRecording.setIdle(value)", value)

        def click(selector):
            idle(False)
            locator = page.locator(selector)
            box = locator.bounding_box()
            if not box:
                raise RuntimeError(f"Missing click target: {selector}")
            if box["y"] < 12 or box["y"] + box["height"] > RECORD_SIZE["height"] - 12:
                locator.evaluate("el => el.scrollIntoView({behavior:'smooth',block:'center',inline:'nearest'})")
                page.wait_for_timeout(850)
                box = locator.bounding_box()
            end = [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2]
            start = pointer.copy()
            for step in range(1, 27):
                t = step / 26
                eased = t * t * (3 - 2 * t)
                page.mouse.move(start[0] + (end[0] - start[0]) * eased, start[1] + (end[1] - start[1]) * eased)
                page.wait_for_timeout(13)
            pointer[:] = end
            page.mouse.down()
            page.wait_for_timeout(90)
            page.mouse.up()
            page.wait_for_timeout(350)
            record("click", target=selector, x=round(end[0]), y=round(end[1]))

        page.goto(base_url + "/?new=1", wait_until="networkidle")
        page.wait_for_function("window.demoRecording && !document.getElementById('start').disabled && document.querySelectorAll('.sample-card').length === 3")
        idle(False)
        page.mouse.move(*pointer)
        record("dashboard_opened")
        page.wait_for_timeout(1300)
        click("#subject")
        page.locator("#subject").select_option(SUBJECT_CODE)
        page.keyboard.press("Escape")
        record("subject_selected", code=SUBJECT_CODE)
        page.wait_for_timeout(650)
        page.screenshot(path=str(OUTPUT_DIR / "01-dashboard.png"))
        with page.expect_response(lambda response: response.url.endswith("/api/jobs") and response.request.method == "POST") as response:
            click("#start")
        submitted = response.value.json()
        if response.value.status != 202:
            raise RuntimeError(f"Generation was not started: {submitted}")
        job_id = submitted["job"]["id"]
        record("generation_started", job_id=job_id)
        deadline, last_sequence = time.monotonic() + MAX_RUN_SECONDS, -1
        while time.monotonic() < deadline:
            idle(True)
            state = page.request.get(f"{base_url}/api/jobs/{job_id}").json()["job"]
            sequence = state["events"][-1]["sequence"] if state["events"] else 0
            if sequence != last_sequence:
                last_sequence = sequence
                idle(False)
                for node in state["stages"]:
                    signature = f"{node['id']}:{node['status']}"
                    if node["status"] != "pending" and signature not in observed:
                        observed.add(signature)
                        record("stage_observed", stage=node["id"], status=node["status"], metrics=node.get("metrics", {}))
                        page.screenshot(path=str(OUTPUT_DIR / f"stage-{node['id']}-{node['status']}.png"))
                last = state["events"][-1] if state["events"] else {}
                if last.get("metrics", {}).get("artifact_id"):
                    record("artifact_preview_updated", artifact=last["metrics"]["artifact_id"])
                page.wait_for_timeout(1300)
            if state["status"] == "error":
                raise RuntimeError(state["error"])
            if state["status"] == "success":
                break
            page.wait_for_timeout(900)
        else:
            raise TimeoutError(f"Job {job_id} remains live; inspect it before starting another")
        idle(False)
        page.wait_for_function("document.getElementById('current-label').textContent === '本次生成'")
        assert all(node.get("result") and not node["result"].get("preview_error") for node in state["stages"])
        record("generation_completed", job_id=job_id, report=state["report"])
        for stage in config["stages"]:
            click(f".node[data-stage='{stage['id']}']")
            page.wait_for_timeout(1700)
            page.screenshot(path=str(OUTPUT_DIR / f"node-{stage['id']}-result.png"))
            record("node_result_reviewed", stage=stage["id"])
        click("#follow-stage")
        page.screenshot(path=str(OUTPUT_DIR / "02-completed-workflow.png"))
        click("#preview")
        page.wait_for_function("document.getElementById('page-image').complete && document.getElementById('page-image').naturalWidth > 0")
        page.wait_for_timeout(1700)
        page.screenshot(path=str(OUTPUT_DIR / "03-word-cover.png"))
        record("word_preview_opened")
        click("#page-number")
        page.keyboard.press("Control+A")
        page.keyboard.type("5", delay=130)
        page.keyboard.press("Tab")
        page.wait_for_timeout(1900)
        page.screenshot(path=str(OUTPUT_DIR / "04-word-ranking.png"))
        record("word_ranking_page_viewed")
        click("#last-page")
        page.wait_for_timeout(1700)
        page.screenshot(path=str(OUTPUT_DIR / "05-esi-and-conclusions.png"))
        record("esi_and_short_recommendations_viewed")
        click("#charts-tab")
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUTPUT_DIR / "06-chart-preview.png"))
        record("analysis_chart_viewed")
        click("#close-viewer")
        with page.expect_download() as download:
            click("#download")
        download.value.save_as(str(OUTPUT_DIR / "generated-environment-report.docx"))
        record("word_downloaded")
        previous = page.locator(".sample-card").evaluate_all("rows=>rows.map(row=>row.dataset.reportId)")
        click("#sample")
        page.wait_for_function("old=>{const ids=Array.from(document.querySelectorAll('.sample-card')).map(row=>row.dataset.reportId);return ids.length===3&&ids.every(id=>!old.includes(id));}", arg=previous)
        record("random_reports_sampled", reports=page.locator(".sample-card").evaluate_all("rows=>rows.map(row=>({id:row.dataset.reportId,text:row.innerText}))"))
        click(".sample-card:first-child")
        click("#page-number")
        page.keyboard.press("Control+A")
        page.keyboard.type("5", delay=130)
        page.keyboard.press("Tab")
        page.wait_for_timeout(1700)
        page.screenshot(path=str(OUTPUT_DIR / "07-random-report-review.png"))
        record("random_report_reviewed")
        click("#close-viewer")
        page.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
        page.wait_for_timeout(1800)
        assert not errors, errors
        record("recording_finished")
        video = page.video
        context.close()
        video_path = Path(video.path())
        browser.close()
    continuous = OUTPUT_DIR / "operation-full.webm"
    video_path.replace(continuous)
    metadata = convert_video(continuous, OUTPUT_DIR / "operation-full.mp4")
    assert hashlib.sha256(request_path.read_bytes()).hexdigest() == request_hash
    write_json(OUTPUT_DIR / "delivery_manifest.json", {"status": "pass", "job_id": job_id, "report_id": state["report"]["id"],
              "recorded_at": now(), "video": str(OUTPUT_DIR / "operation-full.mp4"), "video_metadata": metadata,
              "full_webm": str(continuous), "downloaded_docx": str(OUTPUT_DIR / "generated-environment-report.docx"),
              "pace_marker": "black_corner_idle_white_corner_active", "request_config_unchanged": True,
              "browser_errors": errors, "observed_states": sorted(observed), "actions": actions})
    record("video_saved", video_metadata=metadata)


if __name__ == "__main__":
    main()
