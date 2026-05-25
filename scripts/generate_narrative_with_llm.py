from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import agent_runtime
import build_word_replacement_trial as word_trial


PROJECT_DIR = Path(__file__).resolve().parent.parent
PROMPT_TEMPLATE_PATH = PROJECT_DIR / "configs" / "template_slot_inventory" / "narrative_llm_prompt_template.md"
DEFAULT_SUBJECT_RUN_DIR = PROJECT_DIR / "outputs" / "subject_agent_runs" / "_set_subject_run_dir_explicitly"

# 显式变量保留给单独调试使用；正式流水线会通过 build_subject_word_report.py 传入 run_dir/profile。
SUBJECT_RUN_DIR = DEFAULT_SUBJECT_RUN_DIR
MAX_SOURCE_ROWS_INLINE = 40
MAX_SAMPLE_ROWS = 12


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")


def deep_get(payload: dict[str, Any], dotted_key: str, default: Any = None) -> Any:
    return agent_runtime.deep_get(payload, dotted_key, default)


def runtime_bool(profile: dict[str, Any], dotted_key: str, default: bool) -> bool:
    return agent_runtime.coerce_bool(deep_get(profile, dotted_key, default), default)


def runtime_int(profile: dict[str, Any], dotted_key: str, default: int) -> int:
    value = deep_get(profile, dotted_key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def runtime_float(profile: dict[str, Any], dotted_key: str, default: float) -> float:
    value = deep_get(profile, dotted_key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def runtime_str(profile: dict[str, Any], dotted_key: str, default: str) -> str:
    value = deep_get(profile, dotted_key, default)
    return clean_text(value) or default


def chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    size = max(1, size)
    return [items[index : index + size] for index in range(0, len(items), size)]


def read_csv_preview(path: Path) -> dict[str, Any]:
    import csv

    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = list(reader.fieldnames or [])
        for row in reader:
            rows.append({key: clean_text(value) for key, value in row.items()})

    tongji_rows = [
        row
        for row in rows
        if any("同济" in clean_text(value) or "Tongji" in clean_text(value) for value in row.values())
    ]
    selected_rows: list[dict[str, str]] = []
    if len(rows) <= MAX_SOURCE_ROWS_INLINE:
        selected_rows = rows
    else:
        for row in tongji_rows[:MAX_SAMPLE_ROWS]:
            selected_rows.append(row)
        for row in rows[:6] + rows[-6:]:
            if row not in selected_rows:
                selected_rows.append(row)
        selected_rows = selected_rows[:MAX_SOURCE_ROWS_INLINE]

    return {
        "filename": path.name,
        "row_count": len(rows),
        "columns": columns,
        "selected_rows": selected_rows,
        "tongji_row_count": len(tongji_rows),
    }


def read_json_preview(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    compact = payload
    if isinstance(payload, dict):
        compact = {
            key: value
            for key, value in payload.items()
            if key
            in {
                "title",
                "subtitle",
                "source_system",
                "source_kind",
                "ranking_source",
                "subject",
                "subject_area",
                "external_source",
                "peer_artifact_id",
                "metric_scope",
                "notes",
            }
        }
    return {"filename": path.name, "content": compact}


def source_file_summaries(task: dict[str, Any]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for source_file in task.get("source_files", []):
        path = Path(str(source_file))
        if not path.exists():
            continue
        if path.suffix.lower() == ".csv":
            try:
                summaries.append(read_csv_preview(path))
            except Exception as exc:
                summaries.append({"filename": path.name, "error": f"csv_preview_failed: {exc}"})
        elif path.suffix.lower() == ".json":
            try:
                summaries.append(read_json_preview(path))
            except Exception as exc:
                summaries.append({"filename": path.name, "error": f"json_preview_failed: {exc}"})
    return summaries


def computed_rule_summary(run_dir: Path, task: dict[str, Any]) -> str:
    word_trial.SUBJECT_RUN_DIR = run_dir
    row = {
        "logical_slot_id": clean_text(task.get("logical_slot_id")),
        "artifact_id": clean_text(task.get("artifact_id")),
        "slot_kind": clean_text(task.get("slot_kind")),
    }
    try:
        return clean_text(word_trial.fallback_narrative_text(row, clean_text(task.get("segment_key"))))
    except Exception as exc:
        return f"规则摘要生成失败：{exc}"


def interpretation_guardrails(task: dict[str, Any]) -> list[str]:
    artifact_id = clean_text(task.get("artifact_id"))
    if artifact_id == "figure_02_ranking_indicator_commonality":
        return [
            "该图右侧聚类数值表示跨榜单的覆盖强度或对应口径权重合计，不是某一个排名的单项权重。",
            "不要把右侧聚类值归因到 THE、QS、软科或 U.S.News 单一榜单。",
            "不要写成科研论文在每个榜单中都占比最高；QS更偏声誉，THE较均衡，软科和U.S.News更偏科研论文。",
            "适合写共同评价重心和榜单侧重差异，不适合据此判断同济在某类指标上的表现强弱。",
        ]
    if "indicator_weight" in artifact_id:
        guards = [
            "权重图只说明评价体系如何分配权重，不直接说明同济在该指标上的表现。",
            "优先使用 computed_data_summary 中已经给出的一级指标合计；不要自行创造新的二级指标合计。",
        ]
        if artifact_id == "figure_05_usnews_indicator_weight":
            guards.append("U.S.News权重段落只写一级指标合计，例如科研/论文65%、声誉25%、国际化/合作10%；不要再拆成引用相关或产出量相关的新合计。")
        return guards
    if artifact_id == "figure_07_all_rankings_history":
        return [
            "排名数值越小通常表示位次越靠前；区间排名只能判断大致区间变化。",
            "不同排名的学科口径和指标体系不同，趋势对比应避免写成完全同口径横向比较。",
        ]
    if "peer_indicator" in artifact_id:
        return [
            "相对排名用于说明同济在对标高校中的位置，不能直接等同于全球绝对排名。",
            "可指出相对靠前和相对滞后的指标，但不要把缺少可比样本解释为真实短板。",
        ]
    if artifact_id.startswith(("figure_13", "figure_14", "figure_15", "figure_16")):
        guards = [
            "论文指标需区分数量、质量、占比和国际合作，不要用单一论文规模替代质量判断。",
            "如使用 CWTS 或宽领域数据，应保留代理口径边界。",
        ]
        if artifact_id == "figure_15_paper_highly_cited_relative_rank":
            guards.append("如果数据列为 highly_cited_papers，应表述为高被引论文；只有出现 documents_top_10 或 P_top_10 字段时才写 Top 10% 论文。")
        return guards
    if artifact_id.startswith("table_"):
        return [
            "表格段落应概括分布和对标位置，不要逐行复述。",
            "如样本数量有限，应写成当前可比样本范围内的判断。",
        ]
    return [
        "围绕图表能够直接支撑的结论展开，不要扩展到未提供证据的治理建议或原因判断。",
    ]


def enrich_task(run_dir: Path, task: dict[str, Any]) -> dict[str, Any]:
    keep_keys = [
        "logical_slot_id",
        "artifact_id",
        "slot_kind",
        "segment_key",
        "reference_caption",
        "template_paragraph_index",
        "position_relative_to_caption",
        "generation_hint",
        "template_text",
        "artifact_narrative",
        "template_mode",
        "requires_disclosure",
        "disclosure_text",
        "word_assembly_decision",
    ]
    enriched = {key: task.get(key, "") for key in keep_keys}
    enriched["computed_data_summary"] = computed_rule_summary(run_dir, task)
    enriched["interpretation_guardrails"] = interpretation_guardrails(task)
    enriched["numeric_use_policy"] = (
        "Use computed_data_summary as the primary source of numeric conclusions. "
        "Use source_file_summaries only for verification; do not create new sums or ratios from raw rows."
    )
    enriched["source_file_summaries"] = source_file_summaries(task)
    return enriched


def output_schema_text() -> str:
    return (
        "必须只返回 JSON 对象，结构为："
        '{"segment_texts":[{"logical_slot_id":"L001","artifact_id":"figure_x",'
        '"segment_key":"main","text":"可直接写入 Word 的中文分析段落"}]}。'
        "不得输出 Markdown、解释文字或代码块。"
    )


def system_prompt() -> str:
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8").strip()
    return (
        f"{template}\n\n"
        "额外要求：这些段落面向学校或学院上级阅读，不能只复述图表，要给出克制、可追溯的分析判断。"
        "可以基于指标结构、相对位次、趋势和口径边界解释优势、短板和管理含义，但不得编造输入中没有的数值、学校或因果关系。"
        "如果数据只支持描述覆盖关系或代理口径，就写成口径说明和审慎判断，不写成确定性排名结论。"
        "必须以 computed_data_summary 作为主事实底稿；source_file_summaries 只用于核验和理解口径。"
        "不要从 source_file_summaries 中重新组合新的数字结论，除非 computed_data_summary 已经给出该结论。"
        "不要把 computed_data_summary 逐字改写成报数清单，但必须保留其中的关键事实和判断方向。"
        "权重和共性图优先说明评价体系关注什么、对学科建设意味着什么，再选择少量关键数值作为依据。"
        "跨多个排名汇总的百分比只能表述为跨榜单覆盖强度或对应口径权重合计，不要写成某一个排名的单项权重。"
        "除非原段落就是数据来源说明，不要把句子主要篇幅用于罗列数据源。"
        "不要自行重新计算、四舍五入或合并二级指标；除非 computed_data_summary 已经明示该合计值。"
        "如果需要说明某类指标较重，可以用“占比较高”“权重集中”等定性判断替代新的合计数字。"
        "谨慎使用“超过一半”“过半”“多数”“接近”等隐含量化表述；除非事实底稿已经直接支持。"
        "每段只保留支撑结论所必需的关键数值，通常不超过三个数值。"
    )


def build_user_payload(bundle: dict[str, Any], tasks: list[dict[str, Any]], batch_index: int, batch_count: int) -> str:
    payload = {
        "batch_index": batch_index,
        "batch_count": batch_count,
        "subject_run_dir": bundle.get("subject_run_dir", ""),
        "template_policy": bundle.get("template_policy", {}),
        "writing_goal": "生成可直接进入 Word 正文的图表分析段落，面向上级汇报阅读。",
        "output_schema": output_schema_text(),
        "tasks": tasks,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_json_response(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        value = value[start : end + 1]
    return json.loads(value)


def call_openai_compatible(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    max_output_tokens: int,
    timeout_seconds: int,
) -> dict[str, Any]:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_output_tokens,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM request failed with HTTP {exc.code}: {detail}") from exc


def generated_text_by_key(segment_texts: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for item in segment_texts:
        key = (clean_text(item.get("logical_slot_id")), clean_text(item.get("segment_key")))
        if key[0] and key[1]:
            result[key] = item
    return result


def evidence_text_for_task(task: dict[str, Any]) -> str:
    return json.dumps(task, ensure_ascii=False)


def numeric_tokens(text: str) -> set[str]:
    return set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", text))


def evidence_has_number(token: str, evidence_numbers: set[str]) -> bool:
    if token in evidence_numbers:
        return True
    bare = token.rstrip("%")
    if bare in evidence_numbers:
        return True
    try:
        numeric_value = float(bare)
    except ValueError:
        return False
    variants = {
        str(int(numeric_value)) if numeric_value.is_integer() else str(numeric_value),
        f"{numeric_value:.1f}".rstrip("0").rstrip("."),
        f"{numeric_value:.2f}".rstrip("0").rstrip("."),
        f"{numeric_value:.3f}".rstrip("0").rstrip("."),
    }
    normalized_evidence = {item.rstrip("%") for item in evidence_numbers}
    if bool(variants & normalized_evidence):
        return True
    for item in normalized_evidence:
        try:
            if abs(float(item) - numeric_value) < 0.0001:
                return True
        except ValueError:
            continue
    return False


def validate_segments(tasks: list[dict[str, Any]], segment_texts: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    by_key = generated_text_by_key(segment_texts)
    expected_keys = [(clean_text(task.get("logical_slot_id")), clean_text(task.get("segment_key"))) for task in tasks]
    forbidden_patterns = [
        r"作为AI",
        r"无法生成",
        r"请提供",
        r"Markdown",
        r"JSON",
        r"\btask\b",
        r"数据预览",
        r"模板",
        r"占位",
    ]

    for task in tasks:
        key = (clean_text(task.get("logical_slot_id")), clean_text(task.get("segment_key")))
        item = by_key.get(key)
        if item is None:
            issues.append({"severity": "P0", "key": "|".join(key), "message": "missing generated segment"})
            continue
        text = clean_text(item.get("text"))
        if not text:
            issues.append({"severity": "P0", "key": "|".join(key), "message": "empty generated text"})
            continue
        if text.startswith(("#", "-", "·", "*")):
            issues.append({"severity": "P1", "key": "|".join(key), "message": "text looks like Markdown or bullet"})
        if len(text) > 520:
            issues.append({"severity": "P1", "key": "|".join(key), "message": f"text is too long: {len(text)} chars"})
        for pattern in forbidden_patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                issues.append({"severity": "P1", "key": "|".join(key), "message": f"forbidden wording matched: {pattern}"})
        evidence_numbers = numeric_tokens(evidence_text_for_task(task))
        for token in sorted(numeric_tokens(text)):
            if not evidence_has_number(token, evidence_numbers):
                issues.append({"severity": "P2", "key": "|".join(key), "message": f"number not found in evidence: {token}"})

    extra_keys = sorted(set(by_key) - set(expected_keys))
    for key in extra_keys:
        issues.append({"severity": "P1", "key": "|".join(key), "message": "unexpected generated segment"})

    severities = {issue["severity"] for issue in issues}
    return {
        "status": "failed" if "P0" in severities or "P1" in severities else ("pass_with_warnings" if issues else "passed"),
        "task_count": len(tasks),
        "segment_count": len(segment_texts),
        "issue_count": len(issues),
        "issues": issues,
    }


def repair_ungrounded_segments(
    tasks: list[dict[str, Any]],
    segment_texts: list[dict[str, Any]],
    validation: dict[str, Any],
) -> dict[str, Any]:
    risky_keys = {
        clean_text(issue.get("key"))
        for issue in validation.get("issues", [])
        if issue.get("severity") == "P2" and "number not found in evidence" in clean_text(issue.get("message"))
    }
    if not risky_keys:
        return {"repaired_count": 0, "repaired_keys": []}

    task_by_key = {
        f"{clean_text(task.get('logical_slot_id'))}|{clean_text(task.get('segment_key'))}": task
        for task in tasks
    }
    repaired_keys: list[str] = []
    for item in segment_texts:
        key = f"{clean_text(item.get('logical_slot_id'))}|{clean_text(item.get('segment_key'))}"
        if key not in risky_keys:
            continue
        task = task_by_key.get(key, {})
        replacement = clean_text(task.get("computed_data_summary"))
        if not replacement or replacement.startswith("规则摘要生成失败"):
            continue
        original_text = clean_text(item.get("text"))
        if original_text != replacement:
            item["text"] = replacement
            item["grounding_repair"] = {
                "mode": "computed_data_summary_fallback",
                "reason": "generated_text_contained_numbers_not_found_in_evidence",
            }
            repaired_keys.append(key)
    return {"repaired_count": len(repaired_keys), "repaired_keys": repaired_keys}


def generate_narrative_for_run(run_dir: Path, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = profile or agent_runtime.load_runtime_profile()
    enabled = runtime_bool(profile, "word_pipeline.narrative_llm.enabled", False)
    narrative_dir = run_dir / "narrative_generation"
    bundle_path = narrative_dir / "narrative_generation_bundle.json"
    result_path = narrative_dir / "narrative_generation_result.json"
    validation_path = narrative_dir / "narrative_generation_validation.json"
    debug_path = narrative_dir / "narrative_generation_llm_debug.json"
    if not enabled:
        return {
            "enabled": False,
            "llm_called": False,
            "result_path": str(result_path),
            "validation_path": str(validation_path),
            "status": "skipped",
            "reason": "disabled_by_runtime_profile",
        }
    if not bundle_path.exists():
        raise FileNotFoundError(f"Narrative bundle not found: {bundle_path}")

    api_key_env = runtime_str(profile, "word_pipeline.narrative_llm.api_key_env", "DEEPSEEK_API_KEY")
    api_key = os.environ.get(api_key_env, "").strip()
    if not api_key:
        raise RuntimeError(f"Missing API key environment variable: {api_key_env}")

    base_url = runtime_str(profile, "word_pipeline.narrative_llm.base_url", "https://api.deepseek.com")
    model = runtime_str(profile, "word_pipeline.narrative_llm.model", "deepseek-v4-flash")
    temperature = runtime_float(profile, "word_pipeline.narrative_llm.temperature", 0.25)
    max_output_tokens = runtime_int(profile, "word_pipeline.narrative_llm.max_output_tokens", 3600)
    max_tasks_per_call = runtime_int(profile, "word_pipeline.narrative_llm.max_tasks_per_call", 6)
    timeout_seconds = runtime_int(profile, "word_pipeline.narrative_llm.timeout_seconds", 90)
    fail_on_error = runtime_bool(profile, "word_pipeline.narrative_llm.fail_on_error", True)
    fallback_ungrounded = runtime_bool(profile, "word_pipeline.narrative_llm.fallback_ungrounded_segments", True)

    bundle = read_json(bundle_path)
    raw_tasks = list(bundle.get("tasks", []))
    enriched_tasks = [enrich_task(run_dir, task) for task in raw_tasks]
    all_segments: list[dict[str, Any]] = []
    raw_responses: list[dict[str, Any]] = []
    debug_events: list[dict[str, Any]] = []
    batches = chunked(enriched_tasks, max_tasks_per_call)
    prompt = system_prompt()

    for batch_index, batch_tasks in enumerate(batches, start=1):
        user_payload = build_user_payload(bundle, batch_tasks, batch_index, len(batches))
        parsed: dict[str, Any] | None = None
        response_payload: dict[str, Any] = {}
        content = ""
        last_error = ""
        for attempt in range(1, 4):
            retry_note = ""
            if attempt > 1:
                retry_note = (
                    "\n\n注意：上一轮输出不是合法 JSON。请重新生成本批次，"
                    "只返回一个 JSON 对象，不要代码块，不要解释，所有字符串内部的引号必须正确转义。"
                )
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_payload + retry_note},
            ]
            response_payload = call_openai_compatible(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=messages,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                timeout_seconds=timeout_seconds,
            )
            content = clean_text(response_payload.get("choices", [{}])[0].get("message", {}).get("content", ""))
            try:
                parsed = parse_json_response(content)
                break
            except Exception as exc:
                last_error = str(exc)
                debug_events.append(
                    {
                        "batch_index": batch_index,
                        "attempt": attempt,
                        "error": last_error,
                        "content_preview": content[:1200],
                    }
                )
                time.sleep(0.5)
        if parsed is None:
            write_json(debug_path, {"generated_at": now_text(), "events": debug_events})
            raise ValueError(f"LLM response was not valid JSON for batch {batch_index}: {last_error}")
        segments = parsed.get("segment_texts", [])
        if not isinstance(segments, list):
            raise ValueError(f"LLM response missing segment_texts for batch {batch_index}")
        all_segments.extend(segments)
        raw_responses.append(
            {
                "batch_index": batch_index,
                "model": response_payload.get("model", model),
                "usage": response_payload.get("usage", {}),
                "segment_count": len(segments),
            }
        )
        time.sleep(0.2)

    validation = validate_segments(enriched_tasks, all_segments)
    grounding_repair = {"repaired_count": 0, "repaired_keys": []}
    if fallback_ungrounded and validation.get("issues"):
        grounding_repair = repair_ungrounded_segments(enriched_tasks, all_segments, validation)
        if grounding_repair["repaired_count"]:
            validation = validate_segments(enriched_tasks, all_segments)
    result_payload = {
        "generated_at": now_text(),
        "generator": "deepseek_openai_compatible",
        "provider": runtime_str(profile, "word_pipeline.narrative_llm.provider", "deepseek"),
        "model": model,
        "base_url": base_url,
        "subject_run_dir": str(run_dir),
        "bundle_path": str(bundle_path),
        "task_count": len(enriched_tasks),
        "segment_texts": all_segments,
        "raw_response_summaries": raw_responses,
        "grounding_repair": grounding_repair,
        "validation": validation,
    }
    write_json(result_path, result_payload)
    write_json(validation_path, validation)
    write_json(debug_path, {"generated_at": now_text(), "events": debug_events})

    if fail_on_error and validation["status"] == "failed":
        raise RuntimeError(f"Narrative LLM validation failed: {validation_path}")

    return {
        "enabled": True,
        "llm_called": True,
        "provider": runtime_str(profile, "word_pipeline.narrative_llm.provider", "deepseek"),
        "model": model,
        "result_path": str(result_path),
        "validation_path": str(validation_path),
        "validation_status": validation["status"],
        "validation_issue_count": validation["issue_count"],
        "segment_count": len(all_segments),
        "status": "ok",
    }


def main() -> dict[str, Any]:
    profile = agent_runtime.load_runtime_profile()
    result = generate_narrative_for_run(SUBJECT_RUN_DIR, profile)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    main()
