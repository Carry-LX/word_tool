from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(r"E:\projects\water\word_tool")
INVENTORY_DIR = PROJECT_DIR / "configs" / "template_slot_inventory"
REFERENCE_SLOTS_CSV = INVENTORY_DIR / "reference_slots.csv"
REFERENCE_BLOCKS_CSV = INVENTORY_DIR / "reference_blocks.csv"
REGISTRY_PATH = PROJECT_DIR / "configs" / "artifact_registry.yaml"


def load_registered_artifacts() -> set[str]:
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {item["artifact_id"] for item in data.get("artifacts", [])}


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def logical_slots() -> list[dict[str, Any]]:
    return [
        {
            "logical_slot_id": "L001",
            "section": "一、概述",
            "reference_object": "image_001 + caption_002",
            "raw_slot_ids": "image_001;caption_002",
            "slot_kind": "figure",
            "reference_caption": "图1、同济大学xx学科国际排名",
            "reference_media": "media/image1.png",
            "artifact_id": "figure_01_tongji_subject_ranking_overview",
            "artifact_status": "existing_verified_data",
            "data_status": "available",
            "visual_style_status": "needs_restyle",
            "recommended_visual_style": "four_ranking_card_panel",
            "data_basis": "四大榜单最新排名已生成 chart_data/source_trace。",
            "notes": "当前已有数据，但现图形态需改成参考报告中的四大排名卡片。"
        },
        {
            "logical_slot_id": "L002",
            "section": "二、xx学科国际排名指标介绍",
            "reference_object": "image_002 + caption_004",
            "raw_slot_ids": "image_002;caption_004",
            "slot_kind": "figure",
            "reference_caption": "图2、XX学科在世界学科排名中指标共性",
            "reference_media": "media/image2.png",
            "artifact_id": "figure_02_ranking_indicator_commonality",
            "artifact_status": "new_artifact_required",
            "data_status": "available_from_indicator_weight",
            "visual_style_status": "needs_new_style",
            "recommended_visual_style": "sankey_or_flow_commonality",
            "data_basis": "fact_indicator_weight 可汇总四大排名指标组和权重。",
            "notes": "应复刻参考图的桑基/流向结构，展示四大排名指标共性和权重归类。"
        },
        {
            "logical_slot_id": "L003",
            "section": "二、1、软科学科排名",
            "reference_object": "image_003 + caption_006",
            "raw_slot_ids": "image_003;caption_006",
            "slot_kind": "figure",
            "reference_caption": "图3、软科世界一流学科数学指标权重",
            "reference_media": "media/image3.png",
            "artifact_id": "figure_03_arwu_indicator_weight",
            "artifact_status": "new_artifact_required",
            "data_status": "available",
            "visual_style_status": "needs_new_style",
            "recommended_visual_style": "pie_or_donut_weight_chart",
            "data_basis": "fact_indicator_weight 中有软科-数学 9 个权重细项。",
            "notes": "参考图为饼图，需按软科数学权重绘制。"
        },
        {
            "logical_slot_id": "L004",
            "section": "二、2、QS学科排名",
            "reference_object": "image_004 + caption_008",
            "raw_slot_ids": "image_004;caption_008",
            "slot_kind": "figure",
            "reference_caption": "图4、QS学科排名数学指标权重",
            "reference_media": "media/image4.png",
            "artifact_id": "figure_04_qs_indicator_weight",
            "artifact_status": "new_artifact_required",
            "data_status": "available",
            "visual_style_status": "needs_new_style",
            "recommended_visual_style": "pie_weight_chart",
            "data_basis": "fact_indicator_weight 中有 QS-数学 5 个权重指标。",
            "notes": "参考 Word caption 误写为软科，这里在映射中校正为 QS。"
        },
        {
            "logical_slot_id": "L005",
            "section": "二、3、U.S.News学科排名",
            "reference_object": "image_005 + caption_010",
            "raw_slot_ids": "image_005;caption_010",
            "slot_kind": "figure",
            "reference_caption": "图3、U.S.News学科排名数学学科指标权重",
            "reference_media": "media/image5.png",
            "artifact_id": "figure_05_usnews_indicator_weight",
            "artifact_status": "new_artifact_required_after_data_fix",
            "data_status": "data_gap_usnews_math_weight_missing",
            "visual_style_status": "needs_new_style",
            "recommended_visual_style": "tree_weight_diagram",
            "data_basis": "fact_indicator_weight 当前无 US News-数学权重；只有计算机科学、商业与经济等 5 个学科权重。",
            "notes": "不能硬套其他学科权重。需补 US News 数学权重，或由用户确认使用通用/近似口径。"
        },
        {
            "logical_slot_id": "L006",
            "section": "二、4、THE学科排名",
            "reference_object": "image_006 + caption_012",
            "raw_slot_ids": "image_006;caption_012",
            "slot_kind": "figure",
            "reference_caption": "图4、THE世界学科排名自然科学领域指标权重",
            "reference_media": "media/image6.png",
            "artifact_id": "figure_06_the_indicator_weight",
            "artifact_status": "new_artifact_required",
            "data_status": "available",
            "visual_style_status": "needs_new_style",
            "recommended_visual_style": "tree_weight_diagram",
            "data_basis": "fact_indicator_weight 中有 THE-自然科学 23 个权重行，可提取一级/二级指标。",
            "notes": "数学按 THE 理学/自然科学领域口径。"
        },
        {
            "logical_slot_id": "L007",
            "section": "三、xx学科排名历史发展分析",
            "reference_object": "image_007 + caption_014",
            "raw_slot_ids": "image_007;caption_014",
            "slot_kind": "figure",
            "reference_caption": "图5、同济xx学科在世界学科排名中的历史（排名区间的取值中间位次）",
            "reference_media": "media/image7.png",
            "artifact_id": "figure_07_all_rankings_history",
            "artifact_status": "existing_verified_data",
            "data_status": "available",
            "visual_style_status": "needs_restyle",
            "recommended_visual_style": "multi_source_line_chart",
            "data_basis": "figure_07 已生成 13 个历史趋势点。",
            "notes": "需按参考图重绘多榜单折线样式。"
        },
        {
            "logical_slot_id": "L008",
            "section": "三、1、软科学科排名",
            "reference_object": "table_001 + caption_015",
            "raw_slot_ids": "table_001;caption_015",
            "slot_kind": "table",
            "reference_caption": "表3、xx学科在软科排名中的细分指标排名历史",
            "reference_media": "",
            "artifact_id": "table_01_arwu_tongji_indicator_history",
            "artifact_status": "new_artifact_required_after_data_check",
            "data_status": "partial_only_2025_in_processed_indicator_fact",
            "visual_style_status": "needs_word_table_style",
            "recommended_visual_style": "indicator_history_wide_table",
            "data_basis": "fact_ranking_indicator 当前只入库软科-数学-同济 2025 分项指标。",
            "notes": "参考表要求多年历史。需确认原始软科历史文件是否含分项指标，或接受仅最新年。"
        },
        {
            "logical_slot_id": "L009",
            "section": "三、3、U.S.News学科排名",
            "reference_object": "table_002 + caption_017",
            "raw_slot_ids": "table_002;caption_017",
            "slot_kind": "table",
            "reference_caption": "表2、xx学科在U.S.News学科排名中的细分指标排名历史",
            "reference_media": "",
            "artifact_id": "table_02_usnews_tongji_indicator_history",
            "artifact_status": "new_artifact_required_after_data_check",
            "data_status": "partial_only_2026_in_processed_indicator_fact",
            "visual_style_status": "needs_word_table_style",
            "recommended_visual_style": "indicator_history_wide_table",
            "data_basis": "fact_ranking_indicator 当前只入库 US News-数学-同济 2026 分项指标。",
            "notes": "参考表要求多年历史。需补历史分项指标或降级为最新年表。"
        },
        {
            "logical_slot_id": "L010",
            "section": "三、3、U.S.News学科排名",
            "reference_object": "caption_019",
            "raw_slot_ids": "caption_019",
            "slot_kind": "figure_caption_without_embedded_object",
            "reference_caption": "图6、xx学科在U.S.News学科排名中的历史（趋势图分析）",
            "reference_media": "",
            "artifact_id": "figure_10_usnews_indicator_history_trend",
            "artifact_status": "new_artifact_required_after_data_check",
            "data_status": "partial_only_2026_in_processed_indicator_fact",
            "visual_style_status": "needs_new_style",
            "recommended_visual_style": "indicator_history_line_chart",
            "data_basis": "当前只有 US News 最新年分项指标，不能生成多年趋势。",
            "notes": "参考中只有图题未发现对应图片对象，仍需作为槽位处理。"
        },
        {
            "logical_slot_id": "L011",
            "section": "三、4、THE学科排名",
            "reference_object": "table_003 + caption_020",
            "raw_slot_ids": "table_003;caption_020",
            "slot_kind": "table",
            "reference_caption": "表4、xx学科在THE排名中的细分指标排名历史",
            "reference_media": "",
            "artifact_id": "table_03_the_tongji_indicator_history",
            "artifact_status": "new_artifact_required",
            "data_status": "available",
            "visual_style_status": "needs_word_table_style",
            "recommended_visual_style": "indicator_history_wide_table",
            "data_basis": "fact_ranking_indicator 中 THE-理学-同济有 2023/2024/2025/2026 分项指标。",
            "notes": "可完整生成 THE 分项指标历史表。"
        },
        {
            "logical_slot_id": "L012",
            "section": "四、对标高校整体分析",
            "reference_object": "table_004 + caption_022",
            "raw_slot_ids": "table_004;caption_022",
            "slot_kind": "table",
            "reference_caption": "表5、2025年发布的四大国际排名中内地高校位次分布",
            "reference_media": "",
            "artifact_id": "table_04_mainland_rank_band_distribution",
            "artifact_status": "existing_verified_data",
            "data_status": "available",
            "visual_style_status": "needs_word_table_style",
            "recommended_visual_style": "rank_band_distribution_table",
            "data_basis": "table_04 已生成分档矩阵和明细。",
            "notes": "需按 Word 表格样式重排。"
        },
        {
            "logical_slot_id": "L013",
            "section": "四、1、软科学科排名",
            "reference_object": "table_005 + caption_024",
            "raw_slot_ids": "table_005;caption_024",
            "slot_kind": "table",
            "reference_caption": "表7、软科排名中内地高校位于前列的比较",
            "reference_media": "",
            "artifact_id": "table_05_arwu_mainland_peer_ranking",
            "artifact_status": "existing_verified_data",
            "data_status": "available",
            "visual_style_status": "needs_word_table_style",
            "recommended_visual_style": "wide_peer_ranking_table",
            "data_basis": "table_05 已生成软科 peer 宽表和明细。",
            "notes": "需按参考 Word 表格列宽和页向处理。"
        },
        {
            "logical_slot_id": "L014",
            "section": "四、3、U.S.News学科排名",
            "reference_object": "table_006 + caption_026",
            "raw_slot_ids": "table_006;caption_026",
            "slot_kind": "table",
            "reference_caption": "表6、U.S.News排名中内地高校位于前列的比较",
            "reference_media": "",
            "artifact_id": "table_06_usnews_mainland_peer_ranking",
            "artifact_status": "existing_verified_data",
            "data_status": "available",
            "visual_style_status": "needs_word_table_style",
            "recommended_visual_style": "wide_peer_ranking_table",
            "data_basis": "table_06 已生成 US News peer 宽表和明细。",
            "notes": "已解决 US News 学校英文名消歧，后续复用 latest_peer_records。"
        },
        {
            "logical_slot_id": "L015",
            "section": "四、4、THE学科排名",
            "reference_object": "table_007 + caption_028",
            "raw_slot_ids": "table_007;caption_028",
            "slot_kind": "table",
            "reference_caption": "表8、THE排名中内地高校位于前列的比较",
            "reference_media": "",
            "artifact_id": "table_08_the_mainland_peer_ranking",
            "artifact_status": "existing_verified_data",
            "data_status": "available",
            "visual_style_status": "needs_word_table_style",
            "recommended_visual_style": "wide_peer_ranking_table",
            "data_basis": "table_08 已生成 THE peer 宽表和明细。",
            "notes": "数学按 THE 理学/Physical Sciences 领域。"
        },
        {
            "logical_slot_id": "L016",
            "section": "五、1、软科学科排名",
            "reference_object": "image_008 + caption_031",
            "raw_slot_ids": "image_008;caption_031",
            "slot_kind": "figure",
            "reference_caption": "图8、软科排名前200位内地高校分项指标相对排名",
            "reference_media": "media/image8.png",
            "artifact_id": "figure_09_arwu_peer_indicator_relative_rank",
            "artifact_status": "existing_verified_data",
            "data_status": "available",
            "visual_style_status": "needs_restyle",
            "recommended_visual_style": "multi_indicator_small_multiples",
            "data_basis": "figure_09 已生成软科 peer 指标长表。",
            "notes": "当前图只是验证点图，需复刻参考小面板/多指标排名图。"
        },
        {
            "logical_slot_id": "L017",
            "section": "五、3、U.S.News学科排名",
            "reference_object": "image_009 + caption_033",
            "raw_slot_ids": "image_009;caption_033",
            "slot_kind": "figure",
            "reference_caption": "图7、U.S.News排名前200位内地高校分项指标相对排名",
            "reference_media": "media/image9.png",
            "artifact_id": "figure_11_usnews_peer_indicator_relative_rank",
            "artifact_status": "existing_verified_data",
            "data_status": "available_except_weight",
            "visual_style_status": "needs_restyle",
            "recommended_visual_style": "multi_indicator_small_multiples",
            "data_basis": "figure_11 已生成 43 所 peer + 同济参照的 11 个指标长表；数学权重缺失已记录。",
            "notes": "需复刻参考图多指标小面板样式。"
        },
        {
            "logical_slot_id": "L018",
            "section": "五、4、THE学科排名",
            "reference_object": "image_010 + caption_035",
            "raw_slot_ids": "image_010;caption_035",
            "slot_kind": "figure",
            "reference_caption": "图9、THE排名前200位内地高校分项指标相对排名",
            "reference_media": "media/image10.png",
            "artifact_id": "figure_12_the_peer_indicator_relative_rank",
            "artifact_status": "existing_verified_data",
            "data_status": "available",
            "visual_style_status": "needs_restyle",
            "recommended_visual_style": "multi_indicator_small_multiples",
            "data_basis": "figure_12 已生成 18 所 THE peer 的 5 个指标长表和自然科学权重。",
            "notes": "需复刻参考图多指标小面板样式。"
        },
        {
            "logical_slot_id": "L019",
            "section": "六、1、论文整体",
            "reference_object": "image_011 + caption_037",
            "raw_slot_ids": "image_011;caption_037",
            "slot_kind": "figure",
            "reference_caption": "图10、37所内地高校论文及被引总量及相对排名",
            "reference_media": "media/image11.png",
            "artifact_id": "figure_13_paper_output_citation_relative_rank",
            "artifact_status": "new_artifact_required_after_data_import",
            "data_status": "data_gap_no_wos_or_paper_metric_source_found",
            "visual_style_status": "needs_new_style",
            "recommended_visual_style": "paper_metric_multi_panel_rank_line",
            "data_basis": "data/ 下未检索到 WOS、CNCI、论文、被引、国际合著等独立论文指标数据源。",
            "notes": "必须补论文库或用户提供论文指标表，不能用排名表臆造。"
        },
        {
            "logical_slot_id": "L020",
            "section": "六、2、论文质量",
            "reference_object": "image_012 + caption_039",
            "raw_slot_ids": "image_012;caption_039",
            "slot_kind": "figure",
            "reference_caption": "图11、37所内地高校论文CNCI及篇均被引数及相对排名",
            "reference_media": "media/image12.png",
            "artifact_id": "figure_14_paper_cnci_cpp_relative_rank",
            "artifact_status": "new_artifact_required_after_data_import",
            "data_status": "data_gap_no_wos_or_paper_metric_source_found",
            "visual_style_status": "needs_new_style",
            "recommended_visual_style": "paper_quality_multi_panel_rank_line",
            "data_basis": "未发现 CNCI/篇均被引独立数据源。",
            "notes": "需要论文指标数据源。"
        },
        {
            "logical_slot_id": "L021",
            "section": "六、2、论文质量",
            "reference_object": "image_013 + caption_041",
            "raw_slot_ids": "image_013;caption_041",
            "slot_kind": "figure",
            "reference_caption": "图12、37所内地高校高被引TOP论文量及相对排名",
            "reference_media": "media/image13.png",
            "artifact_id": "figure_15_paper_highly_cited_relative_rank",
            "artifact_status": "new_artifact_required_after_data_import",
            "data_status": "data_gap_no_wos_or_paper_metric_source_found",
            "visual_style_status": "needs_new_style",
            "recommended_visual_style": "highly_cited_multi_panel_rank_line",
            "data_basis": "未发现 TOP1%/TOP10% 高被引论文独立数据源。",
            "notes": "需要论文指标数据源。"
        },
        {
            "logical_slot_id": "L022",
            "section": "六、3、国际合著",
            "reference_object": "image_014 + caption_043",
            "raw_slot_ids": "image_014;caption_043",
            "slot_kind": "figure",
            "reference_caption": "图13、37所内地高校国际合著论文占比及相对排名",
            "reference_media": "media/image14.png",
            "artifact_id": "figure_16_paper_international_collab_relative_rank",
            "artifact_status": "new_artifact_required_after_data_import",
            "data_status": "data_gap_no_wos_or_paper_metric_source_found",
            "visual_style_status": "needs_new_style",
            "recommended_visual_style": "international_collab_rank_line",
            "data_basis": "未发现国际合著论文占比独立数据源。",
            "notes": "需要论文指标数据源。"
        },
        {
            "logical_slot_id": "L023",
            "section": "附表",
            "reference_object": "table_008",
            "raw_slot_ids": "table_008",
            "slot_kind": "table",
            "reference_caption": "附表：XX学科对标高校学科排名历史",
            "reference_media": "",
            "artifact_id": "table_09_peer_full_ranking_history_appendix",
            "artifact_status": "new_artifact_required",
            "data_status": "available_from_existing_peer_tables",
            "visual_style_status": "needs_word_table_style",
            "recommended_visual_style": "appendix_extra_wide_peer_history_table",
            "data_basis": "可由 table_05/table_06/table_07/table_08 的 peer records 和 fact_ranking 合并生成。",
            "notes": "该表很宽，Word 中可能需要横向页面或拆分。"
        },
    ]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    INVENTORY_DIR.mkdir(parents=True, exist_ok=True)
    reference_slots = pd.read_csv(REFERENCE_SLOTS_CSV).fillna("")
    reference_blocks = pd.read_csv(REFERENCE_BLOCKS_CSV).fillna("")
    artifacts = load_registered_artifacts()

    logical_rows = logical_slots()
    raw_to_logical: dict[str, dict[str, Any]] = {}
    for row in logical_rows:
        row["artifact_registered_now"] = row["artifact_id"] in artifacts
        row["coverage_decision"] = "covered_existing" if row["artifact_registered_now"] else "covered_by_planned_artifact"
        for raw_id in row["raw_slot_ids"].split(";"):
            raw_to_logical[raw_id] = row

    raw_rows = []
    for _, raw in reference_slots.iterrows():
        raw_id = clean_text(raw["slot_id"])
        logical = raw_to_logical.get(raw_id)
        if logical is None:
            raw_rows.append(
                {
                    "slot_id": raw_id,
                    "slot_type": raw["slot_type"],
                    "block_index": raw["block_index"],
                    "caption_text": raw["caption_text"],
                    "media_target": raw["media_target"],
                    "table_rows": raw["table_rows"],
                    "table_cols": raw["table_cols"],
                    "logical_slot_id": "",
                    "artifact_id": "",
                    "raw_coverage_status": "UNMAPPED_ERROR",
                    "coverage_note": "该原始槽位未被完整映射，需要修复 mapping。",
                }
            )
            continue
        raw_rows.append(
            {
                "slot_id": raw_id,
                "slot_type": raw["slot_type"],
                "block_index": raw["block_index"],
                "caption_text": raw["caption_text"],
                "media_target": raw["media_target"],
                "table_rows": raw["table_rows"],
                "table_cols": raw["table_cols"],
                "logical_slot_id": logical["logical_slot_id"],
                "artifact_id": logical["artifact_id"],
                "raw_coverage_status": "mapped",
                "coverage_note": logical["notes"],
            }
        )

    summary = {
        "reference_raw_slots": int(len(reference_slots)),
        "reference_image_slots": int((reference_slots["slot_type"] == "image").sum()),
        "reference_table_slots": int((reference_slots["slot_type"] == "table").sum()),
        "reference_caption_slots": int((reference_slots["slot_type"] == "caption_or_heading").sum()),
        "logical_slots": len(logical_rows),
        "raw_slots_mapped": sum(1 for row in raw_rows if row["raw_coverage_status"] == "mapped"),
        "raw_slots_unmapped": sum(1 for row in raw_rows if row["raw_coverage_status"] != "mapped"),
        "existing_registered_artifacts_used": sum(1 for row in logical_rows if row["artifact_registered_now"]),
        "planned_new_artifacts": sum(1 for row in logical_rows if not row["artifact_registered_now"]),
        "data_available_or_partial": sum(1 for row in logical_rows if not str(row["data_status"]).startswith("data_gap")),
        "data_gap_slots": sum(1 for row in logical_rows if str(row["data_status"]).startswith("data_gap")),
    }

    write_csv(INVENTORY_DIR / "logical_slot_artifact_mapping.csv", logical_rows)
    write_csv(INVENTORY_DIR / "raw_slot_coverage.csv", raw_rows)
    (INVENTORY_DIR / "coverage_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    missing = [row for row in logical_rows if not row["artifact_registered_now"]]
    data_gaps = [row for row in logical_rows if str(row["data_status"]).startswith("data_gap")]
    partial = [row for row in logical_rows if str(row["data_status"]).startswith("partial")]

    lines = [
        "# Full Slot Artifact Mapping",
        "",
        "本文件覆盖参考 Word 里的全部候选槽位：14 个图片对象、8 个表格对象、22 个图题/表题类段落。",
        "",
        "## Summary",
        "",
        f"- raw_slots: {summary['reference_raw_slots']}",
        f"- image_slots: {summary['reference_image_slots']}",
        f"- table_slots: {summary['reference_table_slots']}",
        f"- caption_slots: {summary['reference_caption_slots']}",
        f"- logical_slots_after_pairing: {summary['logical_slots']}",
        f"- raw_slots_mapped: {summary['raw_slots_mapped']}",
        f"- raw_slots_unmapped: {summary['raw_slots_unmapped']}",
        f"- existing_registered_artifacts_used: {summary['existing_registered_artifacts_used']}",
        f"- planned_new_artifacts: {summary['planned_new_artifacts']}",
        f"- data_gap_slots: {summary['data_gap_slots']}",
        "",
        "## Files",
        "",
        "- `logical_slot_artifact_mapping.csv`：最终逻辑槽位到 artifact 的覆盖表。",
        "- `raw_slot_coverage.csv`：44 个原始槽位逐一映射到逻辑槽位，要求 unmapped 为 0。",
        "- `coverage_summary.json`：覆盖数量摘要。",
        "",
        "## Planned New Artifacts",
        "",
    ]
    for row in missing:
        lines.append(f"- `{row['artifact_id']}`：{row['reference_caption']}；data_status={row['data_status']}")
    lines.extend(["", "## Data Gaps", ""])
    for row in data_gaps:
        lines.append(f"- `{row['artifact_id']}`：{row['notes']}")
    lines.extend(["", "## Partial Data", ""])
    for row in partial:
        lines.append(f"- `{row['artifact_id']}`：{row['notes']}")
    lines.extend(["", "## Existing Artifacts That Need Visual Restyle", ""])
    for row in logical_rows:
        if row["artifact_registered_now"] and row["visual_style_status"] == "needs_restyle":
            lines.append(f"- `{row['artifact_id']}` -> {row['recommended_visual_style']}")
    (INVENTORY_DIR / "full_slot_artifact_mapping.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Include a small machine-readable list of proposed artifact IDs for future registry work.
    proposed_rows = [
        {
            "artifact_id": row["artifact_id"],
            "slot_kind": row["slot_kind"],
            "reference_caption": row["reference_caption"],
            "data_status": row["data_status"],
            "recommended_visual_style": row["recommended_visual_style"],
        }
        for row in missing
    ]
    write_csv(INVENTORY_DIR / "proposed_new_artifacts.csv", proposed_rows)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
