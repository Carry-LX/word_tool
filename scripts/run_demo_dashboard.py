"""Local dashboard. Configuration lives in the runtime profile, without CLI flags."""
from __future__ import annotations

import copy
import ctypes
import os
import subprocess
import threading
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, send_from_directory

from demo_catalog import catalog, public_report, sample_reports, subjects
from demo_runtime import PROJECT_DIR, configuration, job_root, now, read_json, write_json

FRONTEND = PROJECT_DIR / "frontend/demo"
AUTO_OPEN_BROWSER = os.environ.get("REPORT_DEMO_OPEN_BROWSER", "0") == "1"


def process_alive(pid: int) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        code = ctypes.c_ulong()
        try:
            kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
            return code.value == 259
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


class Jobs:
    def __init__(self):
        self.lock = threading.RLock()
        self.processes: dict[str, subprocess.Popen] = {}

    def read(self, identifier: str) -> dict:
        with self.lock:
            return self._read(identifier)

    def _read(self, identifier: str) -> dict:
        if len(identifier) != 32 or any(char not in "0123456789abcdef" for char in identifier):
            return {}
        state_path = job_root() / identifier / "state.json"
        state = read_json(state_path)
        if state and state["status"] in {"pending", "running"}:
            process = self.processes.get(identifier)
            live = process.poll() is None if process else process_alive(state.get("pid", 0))
            if not live:
                # Read once more after process exit: its final atomic write may have won the race.
                state = read_json(state_path)
                if state["status"] in {"pending", "running"}:
                    state.update(status="error", error="生成进程已结束，请查看运行日志。", finished_at=now())
                    for node in state["stages"]:
                        if node["status"] == "running":
                            node.update(status="error", message=state["error"])
                    write_json(state_path, state)
        return state

    def all(self) -> list[dict]:
        if not job_root().is_dir():
            return []
        rows = [self.read(path.parent.name) for path in job_root().glob("*/state.json")]
        return sorted([row for row in rows if row], key=lambda row: row["created_at"], reverse=True)

    def start(self, subject: dict) -> dict:
        with self.lock:
            active = next((row for row in self.all() if row["status"] in {"pending", "running"}), None)
            if active:
                return {"conflict": active}
            config = configuration()
            identifier = uuid.uuid4().hex
            directory = job_root() / identifier
            directory.mkdir(parents=True)
            runtime = read_json(PROJECT_DIR / "configs/runtime/agent_runtime_profile.json")
            scoped_request = copy.deepcopy(read_json(PROJECT_DIR / runtime["active_subject_request_path"]))
            scoped_request["request"].update(target_subject=subject["name"], target_subject_code=subject["code"],
                                              target_college=subject["college"])
            scoped_request["generated_at"] = now()
            write_json(directory / "request.json", scoped_request)
            state = {"id": identifier, "status": "pending", "created_at": now(), "updated_at": now(),
                     "subject": subject, "university": config["university"], "events": [],
                     "stages": [dict(node, status="pending", message="等待执行", metrics={}) for node in config["stages"]]}
            write_json(directory / "state.json", state)
            env = dict(os.environ, REPORT_DEMO_JOB_DIR=str(directory), PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            try:
                with (directory / "worker.log").open("wb") as log:
                    process = subprocess.Popen([config["python"], "-B", str(PROJECT_DIR / "scripts/demo_worker.py")],
                                               cwd=PROJECT_DIR, env=env, stdout=log, stderr=subprocess.STDOUT,
                                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                self.processes[identifier] = process
            except Exception as error:
                state.update(status="error", error=str(error), finished_at=now())
                write_json(directory / "state.json", state)
                raise
            return state


def public_job(state: dict) -> dict:
    result = copy.deepcopy({key: value for key, value in state.items() if key != "pid"})
    for node in result.get("stages", []):
        for item in node.get("result", {}).get("images", []):
            item.pop("path", None)
            item["url"] = f"/api/jobs/{state['id']}/outputs/{item['id']}"
    if result.get("report"):
        result["report"] = public_report(result["report"])
    return result


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.json.ensure_ascii = False
    jobs = Jobs()
    historical = catalog()
    choices = subjects()
    config = configuration()

    def reports():
        fresh = [state["report"] for state in jobs.all() if state.get("status") == "success" and state.get("report")]
        return fresh + historical

    def find_report(identifier):
        row = next((row for row in reports() if row["id"] == identifier), None)
        if not row:
            abort(404)
        return row

    @app.before_request
    def local_origin():
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and origin != request.host_url.rstrip("/"):
                return jsonify(error="请从本机演示页面操作。"), 403
            if not request.is_json:
                return jsonify(error="需要JSON请求。"), 415

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return send_from_directory(FRONTEND, "index.html")

    @app.get("/assets/<path:filename>")
    def assets(filename):
        return send_from_directory(FRONTEND, filename)

    @app.get("/api/bootstrap")
    def bootstrap():
        rows = reports()
        _, pool_size = sample_reports(rows, config["default_sample_count"])
        latest = next(iter(jobs.all()), None)
        runtime = read_json(PROJECT_DIR / "configs/runtime/agent_runtime_profile.json")
        policy = read_json(PROJECT_DIR / runtime["word_pipeline"]["editorial_policy_path"])
        return jsonify(university=config["university"], subjects=choices, default_subject_code=config["default_subject_code"], esi_subject_codes=list(policy["bindings"]),
                       stages=config["stages"], report_count=len(rows), sample_pool_count=pool_size,
                       sample_count=config["default_sample_count"], latest_job=public_job(latest) if latest else None)

    @app.get("/api/health")
    def health():
        return jsonify(app_id="subject-report-demo", version=2)

    @app.get("/api/reports")
    def report_list():
        return jsonify(reports=[public_report(row) for row in reports()])

    @app.get("/api/reports/<identifier>")
    def report_detail(identifier):
        row = find_report(identifier)
        return jsonify(**public_report(row), pages=[f"/api/files/{identifier}/page/{index}" for index in range(len(row["pages"]))],
                       charts=[f"/api/files/{identifier}/chart/{index}" for index in range(len(row["charts"]))],
                       docx_url=f"/api/files/{identifier}/docx/0", pdf_url=f"/api/files/{identifier}/pdf/0" if row["pdf"] else None)

    @app.get("/api/files/<identifier>/<role>/<int:index>")
    def file(identifier, role, index):
        row = find_report(identifier)
        if role in {"page", "chart"}:
            paths = row["pages" if role == "page" else "charts"]
            if index < 0 or index >= len(paths):
                abort(404)
            path = Path(paths[index])
        elif role in {"docx", "pdf"} and index == 0 and row[role]:
            path = Path(row[role])
        else:
            abort(404)
        if not path.is_file():
            abort(404)
        return send_file(path, as_attachment=role in {"docx", "pdf"}, download_name=path.name)

    @app.post("/api/sample")
    def sample():
        body = request.get_json()
        if not isinstance(body, dict):
            return jsonify(error="请求格式不正确。"), 400
        count = body.get("count", config["default_sample_count"])
        excluded = body.get("exclude", [])
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= config["maximum_sample_count"]:
            return jsonify(error="抽查数量超出范围。"), 400
        if not isinstance(excluded, list) or any(not isinstance(value, str) for value in excluded):
            return jsonify(error="排除列表格式不正确。"), 400
        selected, pool = sample_reports(reports(), count, set(excluded))
        return jsonify(reports=[public_report(row) for row in selected], pool_size=pool,
                       rule=f"完整报告，至少覆盖{config['minimum_sample_source_count']}个榜单，已通过页面检查")

    @app.post("/api/jobs")
    def start_job():
        body = request.get_json()
        subject = next((row for row in choices if row["code"] == body.get("subject_code")), None) if isinstance(body, dict) else None
        if not subject:
            return jsonify(error="请选择列表中的学科。"), 400
        result = jobs.start(subject)
        if "conflict" in result:
            return jsonify(error="已有报告正在生成。", job=public_job(result["conflict"])), 409
        return jsonify(job=public_job(result)), 202

    @app.get("/api/jobs/<identifier>")
    def job_state(identifier):
        state = jobs.read(identifier)
        if not state:
            abort(404)
        return jsonify(job=public_job(state))

    @app.get("/api/jobs/<identifier>/log")
    def job_log(identifier):
        if not jobs.read(identifier):
            abort(404)
        return send_file(job_root() / identifier / "worker.log", as_attachment=True, download_name="generation.log")

    @app.get("/api/jobs/<identifier>/outputs/<file_id>")
    def stage_output(identifier, file_id):
        state = jobs.read(identifier)
        if not state:
            abort(404)
        items = [item for node in state["stages"] for item in node.get("result", {}).get("images", [])]
        item = next((item for item in items if item["id"] == file_id), None)
        if not item:
            abort(404)
        path = Path(item["path"]).resolve()
        if not path.is_relative_to((job_root() / identifier).resolve()) or not path.is_file():
            abort(404)
        return send_file(path)

    app.extensions["demo_jobs"] = jobs
    return app


if __name__ == "__main__":
    config = configuration()
    url = f"http://{config['host']}:{config['port']}"
    print(f"Local report dashboard: {url}", flush=True)
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=2) as response:
            import json
            existing = json.loads(response.read())
        if existing.get("app_id") == "subject-report-demo":
            if AUTO_OPEN_BROWSER:
                import webbrowser
                webbrowser.open(url)
            print("The local dashboard is already running.", flush=True)
            raise SystemExit(0)
    except (OSError, ValueError):
        pass
    if AUTO_OPEN_BROWSER:
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    create_app().run(host=config["host"], port=config["port"], debug=False, threaded=True)
