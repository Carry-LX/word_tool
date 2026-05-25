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
