# Report QA

## Main Gate

Run:

```text
python scripts/audit_release_quality_gate.py
```

Output:

```text
outputs/release_audit/latest/release_quality_gate.json
outputs/release_audit/latest/release_quality_gate.md
```

The gate checks:

- latest Word report exists for each expected report subject
- coverage row count and report-basis count are explicitly recorded
- Word QA status is `pass` or `pass_with_warnings`
- no blank rendered pages
- no sparse rendered pages
- missing-data lineage review has no pipeline or raw utilization issues

The default report basis is `ministry_subject`: one final Word per unique ministry first-level subject/code. The coverage sheet may have more rows than final reports when request subjects borrow a ministry proxy code; those proxy rows are disclosed in the gate metadata instead of being silently counted as separate first-level subject reports.

## Per-Report QA

Each report directory should contain:

```text
qa/word_qa_report.json
qa/word_qa_report.md
qa/rendered_pages/*.png
```

The important fields are:

- `overall_status`
- `warnings`
- `render.page_count`
- `render.blank_pages`
- `render.sparse_pages`

## Warning Policy

`wide_tables_need_visual_review` is allowed for now because several ranking tables are intentionally wide. It should still be visually checked before external delivery.

Any blank page, sparse page, broken docx zip structure, or malformed XML text pattern should block release.

## Regeneration Policy

When a shared mapping, source, or availability rule changes, regenerate only affected subjects first. Use:

```text
scripts/run_subject_report.py
```

Then run:

```text
scripts/audit_release_quality_gate.py
```
