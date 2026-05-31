# Subject Mapping Display/Match Contract

更新时间：2026-05-29

## 核心原则

报告生成时必须区分两类口径：

- `display_alias`：最终写进 Word 正文、图题、表题和图注的榜单学科口径。
- `match_alias` / `data_match_crosswalk`：只用于匹配原始榜单、权重表、历史表或代理数据的内部口径。

如果两者不一致，Word 应展示 `display_alias`，并在 artifact 数据中保留来源字段，例如 `source_ranking_subject_raw`，用于追踪底层数据来自哪个原始口径。

## 主要文件

1. 原始权威映射：

```text
E:\projects\water\word_tool\data\教育部学科与四大国际学科排名映射关系.xlsx
```

2. 核心运行映射：

```text
E:\projects\water\word_tool\processed\dim_subject.csv
E:\projects\water\word_tool\processed\dim_subject_alias.csv
E:\projects\water\word_tool\processed\dim_subject_mapping_explain.csv
```

3. 治理总表：

```text
E:\projects\water\word_tool\processed\mapping_registry.csv
```

`mapping_registry.csv` 中新增字段：

- `mapping_role`
- `display_value`
- `display_norm`
- `match_value`
- `match_norm`

## mapping_role 约定

- `display_alias`：来自 `processed/dim_subject_alias.csv`，可作为 Word 展示口径。
- `match_alias`：来自 `configs/runtime/manual_subject_aliases.json`，只作为数据匹配规则，不能直接替代 Word 展示口径。
- `data_match_crosswalk`：数据源内部口径转换，例如 THE 权重/历史数据的大类匹配。
- `proxy_crosswalk`：代理数据口径转换，例如 CWTS 宽领域论文代理。
- `indicator_normalization`：指标组归并，不属于学科口径展示。

## Sheet1 处理规则

同一个工作簿中的 `Sheet1` 是榜单学科到教育部一级学科的反向映射。处理时需要区分：

- `对应一级学科`：可以按换行、顿号、逗号、分号等拆分，因为一个榜单学科可能对应多个教育部一级学科。
- `榜单学科` / `榜单学科.1`：按原子榜单标签保留，不因名称内部的顿号或逗号拆分。例如 QS `机械、航空和制造工程` 是一个榜单学科名称，不能拆成 `机械` 和 `航空和制造工程` 两个展示口径。

运行时的近邻 proxy 不能覆盖上述展示口径。若只有近邻 proxy 有数据，而 Excel 映射口径无可核验同济记录，应在报告中说明缺失，不强行用 proxy 生成主图或主表。

## 化学示例

原始 Excel 中 `0703 化学`：

```text
软科：化学
QS：化学，化学工程
US News：物理化学 / 化学工程 / 化学
THE：物理学
```

因此 Word 中 THE 展示口径应为：

```text
物理学
```

如果 THE 权重或历史数据源中使用：

```text
自然科学 / Physical Sciences
```

只能作为 `data_match_crosswalk` 的 `match_value`，不能覆盖 Word 中的 `物理学`。

## 快速核查方式

核查某个一级学科对四大榜单的展示口径，优先看：

```text
processed\dim_subject_mapping_explain.csv
```

核查某个值是否只是内部匹配别名，查看：

```text
processed\mapping_registry.csv
```

判断规则：

```text
mapping_role = display_alias          -> 可以展示到 Word
mapping_role = match_alias            -> 只用于匹配
mapping_role = data_match_crosswalk   -> 只用于底层数据口径转换
mapping_role = proxy_crosswalk        -> 代理口径，报告中必须披露
```
