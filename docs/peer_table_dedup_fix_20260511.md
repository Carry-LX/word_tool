# Peer 表重复高校问题修复记录（2026-05-11）

## 问题

计算机科学与技术的 peer 排名表中，同一高校重复出现。例如 US News 表里清华大学、浙江大学等高校会出现多次。

## 原因

这不是图片渲染造成的，而是源数据在学科映射后产生了“一校多口径”记录。以 US News 计算机为例，`subject_0812` 同时映射到：

- `人工智能`
- `计算机科学`
- `工程学`

同一学校可能在这三个榜单口径下都有记录，因此之前 peer 表直接保留所有命中记录时，就会出现同一学校多行。

## 修复

已在 `scripts/subject_artifact_builders.py` 增加公共去重逻辑：

- `university_identity`
- `alias_specificity_score`
- `dedupe_university_rows`

规则：

1. 以英文校名优先、中文校名兜底，识别同一高校。
2. 优先保留更贴近目标学科的记录，例如 `dim_subject_column`、目标学科名、目标榜单口径。
3. 宽泛人工 alias，例如 `Engineering / 工程学`，优先级降低。
4. 若优先级相同，再按排名靠前、总分较高排序。
5. 被合并掉的记录不删除，输出到每个 peer 表目录下的 `deduped_duplicate_records.csv`。

## 验证

重新生成计算机科学与技术：

- `outputs/subject_agent_runs/20260511_110911_0812_计算机科学与技术`

peer 表去重结果：

| 表 | 去重后行数 | 重复高校数 |
| --- | ---: | ---: |
| `table_05_arwu_mainland_peer_ranking` | 66 | 0 |
| `table_06_usnews_mainland_peer_ranking` | 92 | 0 |
| `table_07_qs_mainland_peer_ranking` | 19 | 0 |
| `table_08_the_mainland_peer_ranking` | 23 | 0 |

US News 原先 204 行，去重后 92 行，合并记录 112 行，明细见：

- `outputs/subject_agent_runs/20260511_110911_0812_计算机科学与技术/artifacts/table_06_usnews_mainland_peer_ranking/deduped_duplicate_records.csv`

artifact audit：21 pass / 0 fail。
