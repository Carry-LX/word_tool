"""One real report-generation job in a separate process; no shell commands."""
from __future__ import annotations

import json
import os
import shutil
import traceback
from pathlib import Path

from demo_runtime import PROJECT_DIR, configuration, now, read_json, write_json
from demo_stage_results import StageResults


def main() -> None:
    directory = Path(os.environ["REPORT_DEMO_JOB_DIR"]).resolve()
    config = configuration()
    state_path = directory / "state.json"
    state = read_json(state_path)
    os.environ["SUBJECT_REQUEST_PATH"] = str(directory / "request.json")
    state.update(status="running", pid=os.getpid(), started_at=now())
    write_json(state_path, state)
    sequence = 0
    previews = StageResults(state)

    def save(stage: str, status: str, message: str, metrics: dict | None = None, **extra):
        nonlocal sequence
        metrics = dict(metrics or {}, **extra)
        try:
            preview = previews.make(stage, status, metrics)
        except Exception as error:
            preview = {"title": "结果预览暂不可用", "summary": str(error), "preview_error": str(error)}
            write_json(directory / f"preview_error_{stage}.json", preview)
        if stage == "artifacts" and metrics.get("artifact_id") and metrics.get("artifact_status") == "generated":
            message = f"已生成：{preview['title']}"
        public_metrics = {key: value for key, value in metrics.items()
                          if key not in {"run_dir", "matched_sources", "source_rows", "artifact_output_dir", "docx_path"}}
        sequence += 1
        for node in state["stages"]:
            if node["id"] == stage:
                node.update(status=status, message=message, metrics=public_metrics, result=preview)
                node.setdefault("started_at", now())
                if status in {"success", "error"}:
                    node["finished_at"] = now()
        event = {"sequence": sequence, "stage": stage, "status": status, "message": message,
                 "metrics": public_metrics, "at": now()}
        state["events"].append(event)
        state["updated_at"] = now()
        write_json(state_path, state)
        with (directory / "events.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    try:
        import pipeline_observer
        pipeline_observer.set_observer(save)
        import run_subject_agent as agent
        agent.OUTPUT_DIR = directory / "subject"
        agent.WRITE_GLOBAL_CURRENT_REQUEST = False
        agent.UPDATE_README_ON_RUN = False
        summary = agent.run_subject_agent()
        run_dir = Path(summary["run_dir"])
        if summary.get("subject_artifact_audit", {}).get("fail_count", 0):
            raise RuntimeError("图表审计未通过，请查看运行记录。")
        save("word", "running", "正在组装Word并更新目录")
        import build_subject_word_report as writer
        writer.RUN_SUBJECT_AGENT_FIRST = False
        writer.SUBJECT_RUN_DIR = run_dir
        writer.OUTPUT_ROOT = directory / "report"
        writer.BUILD_NARRATIVE_BUNDLE = True
        writer.GENERATE_NARRATIVE_WITH_LLM = bool(config["enable_narrative_api"])
        writer.USE_DEMO_NARRATIVE_RESULT = False
        writer.RUN_WORD_QA = False
        writer.RUN_RENDER_QA = False
        writer.UPDATE_WORD_FIELDS_WITH_COM = bool(config["update_word_fields"])
        writer.NORMALIZE_DOCX_FOR_WORD_OPEN = False
        result = writer.build_subject_word_report()
        docx = Path(result["word_output_docx"])
        if config["update_word_fields"] and result.get("word_field_update", {}).get("status") != "ok":
            raise RuntimeError("Word目录更新未完成，请查看运行日志。")
        import report_editorial
        policy = report_editorial.load_policy()
        binding = policy["bindings"].get(state["subject"]["code"])
        if binding:
            source = PROJECT_DIR / policy["esi_artifacts_dir"] / binding["esi_key"]
            shutil.copytree(source, docx.parent / "esi_source_bundle", dirs_exist_ok=True)
        save("word", "success", "Word报告已生成", artifact_count=int(summary.get("ready_artifact_count", 0)), docx_path=str(docx))
        save("qa", "running", "正在渲染页面并核查版式", docx_path=str(docx))
        import audit_word_report
        qa = audit_word_report.audit_docx(docx, docx.parent / "qa", render=True)
        if qa["overall_status"] == "fail":
            raise RuntimeError("报告质量检查未通过，请查看运行记录。")
        if qa.get("render", {}).get("sparse_pages"):
            raise RuntimeError("报告包含内容过少的页面，需要检查版式。")
        from demo_catalog import report_record
        report = report_record(docx, qa, state["subject"]["code"], state["subject"]["name"], run_dir, origin="current")
        if not report:
            raise RuntimeError("报告预览文件未生成。")
        state["report"] = report
        state["status"] = "success"
        state["finished_at"] = now()
        save("qa", "success", "检查通过，报告可预览", page_count=report["page_count"], chart_count=report["chart_count"])
    except Exception as error:
        state["status"] = "error"
        state["error"] = str(error)
        state["finished_at"] = now()
        running = next((node["id"] for node in state["stages"] if node["status"] == "running"), "data")
        save(running, "error", str(error))
        (directory / "error.txt").write_text(traceback.format_exc(), encoding="utf-8", newline="\n")
        raise


if __name__ == "__main__":
    main()
