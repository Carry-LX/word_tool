# Data Contract

## Core Tables

The runtime should prefer `processed/ranking.sqlite`. CSV mirrors exist for inspection and fallback.

Important tables:

- `dim_subject`: Ministry first-level subjects and Tongji subject metadata.
- `dim_subject_alias`: Mapping from ranking subject labels to `subject_id`.
- `fact_ranking`: Ranking facts by source, subject, university, year, and rank.
- `fact_ranking_subject_bridge`: Many-to-many bridge from ranking facts to subjects.
- `fact_indicator_weight`: Ranking indicator weights by source and subject/area.
- `fact_ranking_indicator`: Ranking indicator facts by source, subject, university, year, and indicator.
- `fact_ranking_indicator_subject_bridge`: Many-to-many bridge for indicator facts.
- `fact_paper_metric`: WOS/CWTS paper metric facts.

## Query Rule

Do not query subject ranking data by `fact_ranking.subject_id` alone. Many ranking sources use broad areas or one-to-many subject labels.

Use this join rule:

```sql
fact_ranking.ranking_source = dim_subject_alias.ranking_source
AND fact_ranking.ranking_subject_norm = dim_subject_alias.ranking_subject_norm
AND dim_subject_alias.subject_id = :subject_id
```

The same rule applies to indicator facts through the indicator bridge or alias-normalized joins.

## Subject Mapping Display vs Match

Use `processed/dim_subject_mapping_explain.csv` and `processed/dim_subject_alias.csv` as the first source for Word-visible ranking subject labels.

Use `processed/mapping_registry.csv` for governance and lineage. Its `mapping_role` field separates:

- `display_alias`: can be shown in Word as the ranking subject/area label.
- `match_alias`: internal matching alias only; do not use as the Word-visible label.
- `data_match_crosswalk`: internal source-data crosswalk, such as THE display area to THE weight/history area.
- `proxy_crosswalk`: proxy data crosswalk; disclose before using in reports.

Example: if the ministry mapping file says chemistry maps to THE `物理学`, but THE weight data is stored under `自然科学`, Word should display `物理学` and preserve `自然科学` only as source lineage, such as `source_ranking_subject_raw`.

Detailed handoff note:

```text
docs/subject_mapping_display_match_contract_20260529.md
```

## Missing Data Semantics

Use these distinctions in reports and audits:

- `confirmed_no_raw_or_local_tongji_ranking`: Raw/local data does not contain current Tongji ranking for that subject-source pair.
- `latest_year_gap_has_history`: Historical Tongji records exist, but the latest ranking year has no Tongji record.
- `pipeline_issue_*`: Raw or processed data exists, but final availability logic failed to use it. This should block release until fixed.
- `confirmed_no_weight_mapping`: No appropriate indicator weight mapping exists for that source/subject.

## Current Full-Lineage Review

The latest lineage review is produced by:

```text
scripts/audit_missing_data_lineage_review.py
```

Primary outputs:

```text
outputs/missing_data_lineage_review/missing_data_lineage_review_summary.json
outputs/missing_data_lineage_review/source_gap_lineage_review.csv
outputs/missing_data_lineage_review/missing_data_subject_priority.csv
```

Release candidates should have:

```text
potential_pipeline_issue_count = 0
raw_utilization_issue_count = 0
```
