from __future__ import annotations

import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import agent_runtime
import audit_agent_system_readiness
import build_subject_word_report
import run_subject_agent


PROJECT_DIR = Path(__file__).resolve().parent.parent
RUNTIME_PROFILE = agent_runtime.load_runtime_profile()
SUBJECT_REQUEST = agent_runtime.load_subject_request(RUNTIME_PROFILE)
OUTPUT_ROOT = agent_runtime.profile_path(
    RUNTIME_PROFILE,
    "paths.report_agent_runs_dir",
    PROJECT_DIR / "outputs" / "report_agent_runs",
)

# Single explicit entrypoint for the whole report system.
# Edit configs/runtime/current_subject_request.json and configs/runtime/agent_runtime_profile.json
# instead of passing CLI arguments.
RUN_RECOVERY_SELF_TEST = False
RESUME_INCOMPLETE_RUN = agent_runtime.profile_bool(RUNTIME_PROFILE, "report_agent.resume_incomplete_run", True)
RERUN_PASSED_STAGES = agent_runtime.profile_bool(RUNTIME_PROFILE, "report_agent.rerun_passed_stages", False)
STOP_ON_GATE_FAILURE = agent_runtime.profile_bool(RUNTIME_PROFILE, "report_agent.stop_on_gate_failure", True)
ALLOW_DELIVERY_WITH_WARNINGS = agent_runtime.profile_bool(RUNTIME_PROFILE, "report_agent.allow_delivery_with_warnings", True)


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def slug_text(value: Any) -> str:
    text = clean_text(value)
    text = "".join(ch if ch.isalnum() or "\u4e00" <= ch <= "\u9fff" else "_" for ch in text)
    text = "_".join(part for part in text.split("_") if part)
    return text or "subject"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def make_report_agent_dir() -> Path:
    subject_code = clean_text(SUBJECT_REQUEST.get("target_subject_code"))
    subject_name = slug_text(SUBJECT_REQUEST.get("target_subject"))
    run_dir = OUTPUT_ROOT / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{subject_code}_{subject_name}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def initialize_state(agent_run_dir: Path) -> dict[str, Any]:
    return {
        "generated_at": now_text(),
        "updated_at": now_text(),
        "status": "running",
        "agent_run_dir": str(agent_run_dir),
        "objective": "end_to_end_report_agent",
        "profile_path": RUNTIME_PROFILE.get("_profile_path", ""),
        "subject_request_path": SUBJECT_REQUEST.get("_request_path", ""),
        "request": {
            "target_university": SUBJECT_REQUEST.get("target_university", ""),
            "target_subject": SUBJECT_REQUEST.get("target_subject", ""),
            "target_subject_code": SUBJECT_REQUEST.get("target_subject_code", ""),
            "report_year": SUBJECT_REQUEST.get("report_year", ""),
            "ranking_sources": agent_runtime.normalize_ranking_sources(
                SUBJECT_REQUEST.get("ranking_sources"),
                agent_runtime.deep_get(RUNTIME_PROFILE, "execution.ranking_sources", agent_runtime.SUPPORTED_RANKING_SOURCES),
            ),
            "proxy_policy": agent_runtime.request_value(
                SUBJECT_REQUEST,
                "proxy_policy",
                agent_runtime.deep_get(RUNTIME_PROFILE, "governance.proxy_policy", "allow_with_disclosure"),
            ),
        },
        "stages": [],
        "outputs": {},
        "delivery_gate": {},
        "resume": {
            "enabled": RESUME_INCOMPLETE_RUN,
            "rerun_passed_stages": RERUN_PASSED_STAGES,
            "resumed": False,
            "resume_events": [],
        },
    }


def current_request_signature() -> dict[str, Any]:
    return {
        "target_university": SUBJECT_REQUEST.get("target_university", ""),
        "target_subject": SUBJECT_REQUEST.get("target_subject", ""),
        "target_subject_code": SUBJECT_REQUEST.get("target_subject_code", ""),
        "report_year": SUBJECT_REQUEST.get("report_year", ""),
        "ranking_sources": agent_runtime.normalize_ranking_sources(
            SUBJECT_REQUEST.get("ranking_sources"),
            agent_runtime.deep_get(RUNTIME_PROFILE, "execution.ranking_sources", agent_runtime.SUPPORTED_RANKING_SOURCES),
        ),
        "proxy_policy": agent_runtime.request_value(
            SUBJECT_REQUEST,
            "proxy_policy",
            agent_runtime.deep_get(RUNTIME_PROFILE, "governance.proxy_policy", "allow_with_disclosure"),
        ),
    }


def state_matches_current_request(state: dict[str, Any]) -> bool:
    request = state.get("request", {})
    current = current_request_signature()
    return all(request.get(key) == current.get(key) for key in ["target_university", "target_subject", "target_subject_code", "report_year", "proxy_policy"])


def find_resumable_state() -> tuple[Path, dict[str, Any]] | None:
    if not RESUME_INCOMPLETE_RUN or not OUTPUT_ROOT.exists():
        return None
    state_paths = sorted(OUTPUT_ROOT.glob("*/report_agent_state.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for state_path in state_paths:
        if state_path.parent.name.startswith("_"):
            continue
        try:
            state = read_json(state_path)
        except Exception:
            continue
        if state.get("status") == "complete":
            continue
        if not state_matches_current_request(state):
            continue
        return state_path.parent, state
    return None


def load_or_initialize_state() -> tuple[Path, dict[str, Any]]:
    resumable = find_resumable_state()
    if resumable:
        agent_run_dir, state = resumable
        state["status"] = "running"
        state["updated_at"] = now_text()
        state.setdefault("resume", {})
        state["resume"]["enabled"] = RESUME_INCOMPLETE_RUN
        state["resume"]["rerun_passed_stages"] = RERUN_PASSED_STAGES
        state["resume"]["resumed"] = True
        state["resume"].setdefault("resume_events", []).append({"at": now_text(), "event": "resume_existing_state"})
        write_json(agent_run_dir / "report_agent_state.json", state)
        return agent_run_dir, state
    agent_run_dir = make_report_agent_dir()
    state = initialize_state(agent_run_dir)
    write_json(agent_run_dir / "report_agent_state.json", state)
    return agent_run_dir, state


def first_stage_index(state: dict[str, Any], name: str) -> int | None:
    for idx, row in enumerate(state.get("stages", [])):
        if row.get("name") == name:
            return idx
    return None


def existing_stage(state: dict[str, Any], name: str) -> dict[str, Any] | None:
    idx = first_stage_index(state, name)
    if idx is None:
        return None
    return state["stages"][idx]


def prune_stage_and_following(state: dict[str, Any], name: str) -> None:
    idx = first_stage_index(state, name)
    if idx is None:
        return
    removed = [row.get("name") for row in state["stages"][idx:]]
    state["stages"] = state["stages"][:idx]
    state.setdefault("resume", {}).setdefault("resume_events", []).append(
        {"at": now_text(), "event": "prune_failed_or_stale_stage", "from_stage": name, "removed": removed}
    )


def run_stage(
    state: dict[str, Any],
    agent_run_dir: Path,
    name: str,
    fn: Callable[[], dict[str, Any]],
    required: bool = True,
) -> dict[str, Any]:
    existing = existing_stage(state, name)
    if existing and existing.get("status") == "pass" and not RERUN_PASSED_STAGES:
        state.setdefault("resume", {}).setdefault("resume_events", []).append(
            {"at": now_text(), "event": "skip_passed_stage", "stage": name}
        )
        write_json(agent_run_dir / "report_agent_state.json", state)
        return {"status": "pass", "outputs": existing.get("outputs", {}), "issues": existing.get("issues", [])}
    if existing:
        prune_stage_and_following(state, name)
    return append_stage(state, agent_run_dir, name, fn, required=required)


def append_stage(
    state: dict[str, Any],
    agent_run_dir: Path,
    name: str,
    fn: Callable[[], dict[str, Any]],
    required: bool = True,
) -> dict[str, Any]:
    started_at = now_text()
    row: dict[str, Any] = {
        "name": name,
        "required": required,
        "started_at": started_at,
        "finished_at": "",
        "status": "running",
        "outputs": {},
        "issues": [],
        "error": "",
    }
    state["stages"].append(row)
    state["updated_at"] = started_at
    write_json(agent_run_dir / "report_agent_state.json", state)
    try:
        result = fn()
        row["finished_at"] = now_text()
        row["status"] = result.get("status", "pass")
        row["outputs"] = result.get("outputs", {})
        row["issues"] = result.get("issues", [])
        state["outputs"].update(result.get("state_outputs", {}))
        state["updated_at"] = row["finished_at"]
        write_json(agent_run_dir / "report_agent_state.json", state)
        if required and row["status"] == "fail" and STOP_ON_GATE_FAILURE:
            raise RuntimeError(f"Required stage failed: {name}")
        return result
    except Exception as exc:
        row["finished_at"] = now_text()
        row["status"] = "fail"
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["traceback"] = traceback.format_exc()
        state["status"] = "failed"
        state["updated_at"] = row["finished_at"]
        write_json(agent_run_dir / "report_agent_state.json", state)
        raise


def stage_runtime_preflight() -> dict[str, Any]:
    issues = agent_runtime.validate_subject_request(SUBJECT_REQUEST)
    blocking = [row for row in issues if row.get("severity") in {"P0", "P1"}]
    return {
        "status": "fail" if blocking else "pass",
        "issues": issues,
        "outputs": {
            "issue_count": len(issues),
            "blocking_issue_count": len(blocking),
        },
    }


def stage_subject_agent() -> dict[str, Any]:
    summary = run_subject_agent.run_subject_agent()
    run_dir = Path(summary["run_dir"])
    artifact_audit = summary.get("subject_artifact_audit", {})
    fail_count = int(artifact_audit.get("fail_count", 0) or 0)
    return {
        "status": "fail" if fail_count else "pass",
        "issues": [] if fail_count == 0 else [{"severity": "P1", "message": f"artifact audit failed: {fail_count}"}],
        "outputs": {
            "subject_run_dir": str(run_dir),
            "ready_artifact_count": summary.get("ready_artifact_count"),
            "artifact_count": summary.get("artifact_count"),
            "artifact_audit": artifact_audit,
            "agent_decision_summary": summary.get("agent_decision_summary", {}),
        },
        "state_outputs": {
            "subject_run_dir": str(run_dir),
            "subject_agent_summary": str(run_dir / "agent_run_summary.json"),
        },
    }


def stage_chart_image_qa(state: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(state["outputs"]["subject_run_dir"])
    qa_files = sorted(run_dir.glob("artifacts/**/chart_image_qa.json"))
    warnings: list[dict[str, Any]] = []
    missing: list[str] = []
    generation_summary_path = run_dir / "artifacts" / "artifact_generation_summary.json"
    generation_summary = read_json(generation_summary_path) if generation_summary_path.exists() else {}
    for result in generation_summary.get("results", []):
        if result.get("status") != "generated":
            continue
        artifact_dir = Path(result.get("output_dir", ""))
        if not (artifact_dir / "chart_image_qa.json").exists():
            missing.append(clean_text(result.get("artifact_id")))
    for qa_path in qa_files:
        payload = read_json(qa_path)
        if payload.get("warnings"):
            warnings.append(
                {
                    "artifact_id": qa_path.parent.name,
                    "warnings": payload.get("warnings", []),
                    "content_ratio": payload.get("content_ratio"),
                    "margins_px": payload.get("margins_px", {}),
                }
            )
    status = "fail" if warnings or missing else "pass"
    return {
        "status": status,
        "issues": warnings + [{"artifact_id": item, "warnings": ["missing_chart_image_qa"]} for item in missing],
        "outputs": {
            "chart_image_qa_count": len(qa_files),
            "chart_image_warning_count": len(warnings),
            "missing_chart_image_qa_count": len(missing),
        },
    }


def stage_word_report(state: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(state["outputs"]["subject_run_dir"])
    build_subject_word_report.RUN_SUBJECT_AGENT_FIRST = False
    build_subject_word_report.SUBJECT_RUN_DIR = run_dir
    payload = build_subject_word_report.build_subject_word_report()
    qa = payload.get("word_qa", {})
    render = qa.get("render", {})
    zip_status = qa.get("zip", {})
    blocking_issues: list[dict[str, Any]] = []
    if qa.get("overall_status") == "fail":
        blocking_issues.append({"severity": "P1", "message": "word qa failed"})
    if render and render.get("status") != "ok":
        blocking_issues.append({"severity": "P1", "message": "word render failed"})
    if render.get("blank_pages"):
        blocking_issues.append({"severity": "P1", "message": "word has blank pages", "pages": render.get("blank_pages")})
    if render.get("sparse_pages"):
        blocking_issues.append({"severity": "P2", "message": "word has sparse pages", "pages": render.get("sparse_pages")})
    if int(zip_status.get("stale_media_count", 0) or 0) > 0:
        blocking_issues.append({"severity": "P1", "message": "word has stale media"})
    status = "fail" if any(row.get("severity") == "P1" for row in blocking_issues) else "pass"
    return {
        "status": status,
        "issues": blocking_issues,
        "outputs": {
            "word_output_docx": payload.get("word_output_docx"),
            "word_output_dir": payload.get("word_output_dir"),
            "word_overall_status": qa.get("overall_status"),
            "word_warnings": qa.get("warnings", []),
            "page_count": render.get("page_count"),
            "blank_pages": render.get("blank_pages", []),
            "sparse_pages": render.get("sparse_pages", []),
            "stale_media_count": zip_status.get("stale_media_count"),
        },
        "state_outputs": {
            "word_output_docx": payload.get("word_output_docx"),
            "word_summary": str(Path(payload.get("word_output_dir", "")) / "subject_word_report_summary.json"),
        },
    }


def stage_system_readiness() -> dict[str, Any]:
    payload = audit_agent_system_readiness.build_audit()
    issues = payload.get("issues", [])
    blocking = [row for row in issues if row.get("severity") in {"P0", "P1"}]
    return {
        "status": "fail" if blocking else "pass",
        "issues": blocking,
        "outputs": {
            "audit_json": payload.get("outputs", {}).get("json", ""),
            "p0_count": sum(1 for row in issues if row.get("severity") == "P0"),
            "p1_count": sum(1 for row in issues if row.get("severity") == "P1"),
            "p2_count": sum(1 for row in issues if row.get("severity") == "P2"),
        },
        "state_outputs": {
            "system_readiness_audit": payload.get("outputs", {}).get("json", ""),
        },
    }


def stage_delivery_gate(state: dict[str, Any]) -> dict[str, Any]:
    failed_stages = [row for row in state["stages"] if row.get("required") and row.get("status") == "fail"]
    word_stage = next((row for row in state["stages"] if row.get("name") == "word_report"), {})
    word_warnings = word_stage.get("outputs", {}).get("word_warnings", [])
    has_warnings = bool(word_warnings)
    deliverable = not failed_stages and (ALLOW_DELIVERY_WITH_WARNINGS or not has_warnings)
    gate = {
        "deliverable": deliverable,
        "status": "pass" if deliverable else "fail",
        "failed_required_stages": [row["name"] for row in failed_stages],
        "allowed_warnings": word_warnings if ALLOW_DELIVERY_WITH_WARNINGS else [],
        "word_output_docx": state["outputs"].get("word_output_docx", ""),
        "subject_run_dir": state["outputs"].get("subject_run_dir", ""),
    }
    state["delivery_gate"] = gate
    return {
        "status": gate["status"],
        "issues": [] if deliverable else [{"severity": "P1", "message": "delivery gate failed", "gate": gate}],
        "outputs": gate,
    }


def build_markdown_summary(state: dict[str, Any]) -> str:
    lines = [
        "# Report Agent Run",
        "",
        f"- generated_at: {state.get('generated_at', '')}",
        f"- updated_at: {state.get('updated_at', '')}",
        f"- status: {state.get('status', '')}",
        f"- target: {state.get('request', {}).get('target_university', '')} / {state.get('request', {}).get('target_subject', '')}",
        f"- subject_run_dir: {state.get('outputs', {}).get('subject_run_dir', '')}",
        f"- word_output_docx: {state.get('outputs', {}).get('word_output_docx', '')}",
        f"- deliverable: {state.get('delivery_gate', {}).get('deliverable', False)}",
        "",
        "## Stages",
        "",
        "| stage | status | issues |",
        "| --- | --- | ---: |",
    ]
    for row in state.get("stages", []):
        lines.append(f"| {row.get('name', '')} | {row.get('status', '')} | {len(row.get('issues', []))} |")
    return "\n".join(lines) + "\n"


def run_recovery_self_test() -> dict[str, Any]:
    test_dir = OUTPUT_ROOT / "_recovery_self_test"
    test_dir.mkdir(parents=True, exist_ok=True)
    state = initialize_state(test_dir)
    state["status"] = "failed"
    state["stages"] = [
        {
            "name": "runtime_preflight",
            "required": True,
            "started_at": now_text(),
            "finished_at": now_text(),
            "status": "pass",
            "outputs": {"issue_count": 0, "blocking_issue_count": 0},
            "issues": [],
            "error": "",
        },
        {
            "name": "subject_agent",
            "required": True,
            "started_at": now_text(),
            "finished_at": now_text(),
            "status": "fail",
            "outputs": {},
            "issues": [{"severity": "P1", "message": "synthetic failure"}],
            "error": "synthetic failure",
        },
        {
            "name": "chart_image_qa",
            "required": True,
            "started_at": now_text(),
            "finished_at": now_text(),
            "status": "running",
            "outputs": {},
            "issues": [],
            "error": "",
        },
    ]
    write_json(test_dir / "report_agent_state.json", state)
    executed: list[str] = []

    def fake_subject() -> dict[str, Any]:
        executed.append("subject_agent")
        return {
            "status": "pass",
            "outputs": {"subject_run_dir": "synthetic_subject_run"},
            "issues": [],
            "state_outputs": {"subject_run_dir": "synthetic_subject_run"},
        }

    existing = existing_stage(state, "runtime_preflight")
    skipped_runtime = bool(existing and existing.get("status") == "pass")
    run_stage(state, test_dir, "runtime_preflight", lambda: {"status": "fail"}, required=True)
    run_stage(state, test_dir, "subject_agent", fake_subject, required=True)
    result = {
        "status": "pass"
        if skipped_runtime
        and executed == ["subject_agent"]
        and [row["name"] for row in state["stages"]] == ["runtime_preflight", "subject_agent"]
        and state["stages"][-1]["status"] == "pass"
        else "fail",
        "skipped_runtime": skipped_runtime,
        "executed": executed,
        "stage_names": [row["name"] for row in state["stages"]],
        "resume_events": state.get("resume", {}).get("resume_events", []),
    }
    state["status"] = "complete" if result["status"] == "pass" else "failed"
    state["updated_at"] = now_text()
    write_json(test_dir / "report_agent_state.json", state)
    write_json(test_dir / "recovery_self_test_result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def run_report_agent() -> dict[str, Any]:
    agent_run_dir, state = load_or_initialize_state()
    run_stage(state, agent_run_dir, "runtime_preflight", stage_runtime_preflight)
    run_stage(state, agent_run_dir, "subject_agent", stage_subject_agent)
    run_stage(state, agent_run_dir, "chart_image_qa", lambda: stage_chart_image_qa(state))
    run_stage(state, agent_run_dir, "word_report", lambda: stage_word_report(state))
    run_stage(state, agent_run_dir, "system_readiness", stage_system_readiness)
    run_stage(state, agent_run_dir, "delivery_gate", lambda: stage_delivery_gate(state))
    state["status"] = "complete" if state.get("delivery_gate", {}).get("deliverable") else "failed"
    state["updated_at"] = now_text()
    write_json(agent_run_dir / "report_agent_state.json", state)
    write_json(agent_run_dir / "report_agent_summary.json", state)
    (agent_run_dir / "report_agent_summary.md").write_text(build_markdown_summary(state), encoding="utf-8", newline="\n")
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return state


if __name__ == "__main__":
    if RUN_RECOVERY_SELF_TEST:
        run_recovery_self_test()
    else:
        run_report_agent()
