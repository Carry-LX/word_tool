"""Read-only API and browser checks for the local demonstration interface."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from demo_runtime import PROJECT_DIR, configuration, write_json
from run_demo_dashboard import create_app

OUTPUT = PROJECT_DIR / "outputs/web_demo_validation"


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    client = create_app().test_client()
    bootstrap = client.get("/api/bootstrap").json
    latest = bootstrap.get("latest_job")
    stage_results = latest and all(node.get("result") for node in latest["stages"])
    if stage_results:
        for node in latest["stages"]:
            assert not node["result"].get("preview_error")
            for item in node["result"].get("images", []):
                assert "path" not in item and item["url"].startswith(f"/api/jobs/{latest['id']}/outputs/")
                assert client.get(item["url"]).status_code == 200
        assert client.get(f"/api/jobs/{latest['id']}/outputs/unknown").status_code == 404
    assert bootstrap["subjects"] and bootstrap["sample_pool_count"] > 3
    rows = client.get("/api/reports").json["reports"]
    assert not {"geosciences", "social_sciences_general"} & {row["code"] for row in rows}
    assert len([row for row in rows if row["has_esi"] and row["origin"] == "history"]) == 6
    assert client.post("/api/jobs", json={"subject_code": "invalid"}).status_code == 400
    assert client.post("/api/jobs", json=[]).status_code == 400
    assert client.post("/api/sample", json={"count": 0}).status_code == 400
    assert client.post("/api/sample", json={"count": True}).status_code == 400
    assert client.post("/api/sample", json={"count": 999}).status_code == 400
    assert client.post("/api/jobs", json={"subject_code": "0830"}, headers={"Origin": "http://example.com"}).status_code == 403
    assert client.get("/api/jobs/not-a-job").status_code == 404
    first = client.post("/api/sample", json={"count": 3}).json
    second = client.post("/api/sample", json={"count": 3, "exclude": [row["id"] for row in first["reports"]]}).json
    assert not {row["id"] for row in first["reports"]} & {row["id"] for row in second["reports"]}
    for row in first["reports"] + second["reports"]:
        assert row["report_type"] == "full_subject_report" and len(row["sources"]) >= 3
        detail = client.get(f"/api/reports/{row['id']}").json
        assert len(detail["pages"]) == row["page_count"]
        assert client.get(detail["pages"][0]).status_code == 200
        assert client.get(f"/api/files/{row['id']}/page/9999").status_code == 404
        with client.get(detail["docx_url"]) as downloaded:
            assert downloaded.status_code == 200 and downloaded.data.startswith(b"PK")
            assert "attachment" in downloaded.headers["Content-Disposition"]
    config = configuration()
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"http://{config['host']}:{config['port']}", wait_until="networkidle")
        page.locator("#preview").wait_for(state="visible")
        page.wait_for_function("!document.getElementById('preview').disabled && document.querySelectorAll('.sample-card').length === 3")
        assert page.locator(".node").count() == 6
        assert page.locator("#subject option").count() == len(bootstrap["subjects"])
        if stage_results:
            page.locator(".node[data-stage='data']").click()
            assert page.locator(".stage-table tbody tr").count() == 7
            assert page.locator("#follow-stage").get_attribute("aria-pressed") == "false"
            page.locator(".node[data-stage='sources']").click()
            assert page.locator(".stage-table tbody tr").count() == 4
            page.locator(".node[data-stage='artifacts']").click()
            assert page.locator(".stage-picture img").count() == 1
            page.locator("#follow-stage").click()
            assert page.locator("#follow-stage").get_attribute("aria-pressed") == "true"
        page.screenshot(path=str(OUTPUT / "dashboard-desktop.png"), full_page=True)
        page.locator("#preview").click()
        page.wait_for_function("document.getElementById('page-image').complete && document.getElementById('page-image').naturalWidth > 0")
        page.locator("#last-page").click()
        page.wait_for_function("document.getElementById('page-number').value === document.getElementById('page-number').max")
        page.screenshot(path=str(OUTPUT / "report-last-page.png"))
        if page.locator("#charts-tab").is_enabled():
            page.locator("#charts-tab").click()
            page.wait_for_function("document.getElementById('charts-tab').getAttribute('aria-selected') === 'true'")
        page.locator("#close-viewer").click()
        before = page.locator(".sample-card").evaluate_all("rows => rows.map(row => row.dataset.reportId)")
        page.locator("#sample").click()
        page.wait_for_function("old => {const ids = Array.from(document.querySelectorAll('.sample-card')).map(row => row.dataset.reportId); return ids.length === 3 && ids.every(id => !old.includes(id));}", arg=before)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(OUTPUT / "dashboard-mobile.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile horizontal overflow"
        assert not errors, errors
        browser.close()
    write_json(OUTPUT / "smoke_checks.json", {"status": "pass", "report_count": len(rows), "sample_pool_count": first["pool_size"],
                                              "subject_count": len(bootstrap["subjects"]), "browser_errors": errors, "stage_results_checked": bool(stage_results),
                                              "checks": ["six_esi_bindings", "excluded_two_esi_topics", "input_validation", "cross_origin_guard",
                                                         "random_sampling_and_exclusion", "download_bytes", "real_page_preview", "page_and_chart_navigation", "mobile_width"]})
    print(json.dumps({"status": "pass", "output": str(OUTPUT)}, ensure_ascii=True))


if __name__ == "__main__":
    main()
