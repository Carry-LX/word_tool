# Word Tool Agent Architecture

This project generates Tongji University subject ranking reports from structured ranking data, mapping rules, chart/table artifacts, and a Word template.

## Current Main Entrypoints

Use these first:

- `scripts/run_subject_report.py`
- `scripts/run_batch_reports.py`
- `scripts/audit_release_quality_gate.py`
- `scripts/manage_output_lifecycle.py`

Older `build_*` and `audit_*` scripts are still kept for traceability, but new work should route through the main entrypoints above whenever possible.

## Data Flow

```text
data/*.xlsx
  -> scripts/build_processed_core.py
  -> processed/*.csv + processed/ranking.sqlite
  -> scripts/run_subject_agent.py
  -> outputs/subject_agent_runs/<timestamp_code_subject>/
  -> scripts/build_subject_word_report.py
  -> outputs/full_word_reports/<timestamp_code_subject>/*.docx
  -> scripts/audit_release_quality_gate.py
```

## Ranking Source Keys

New code should use canonical ASCII keys internally:

```text
arwu
qs
usnews
the
```

Display labels are only for user-facing text:

```text
软科
QS
US News
THE
```

The compatibility layer is `scripts/ranking_sources.py`. Existing processed CSV files may still contain display labels, so migration should happen at code boundaries rather than by rewriting historical outputs in place.

## Subject Report Basis

The Tongji coverage sheet currently has 49 rows, but several rows are source request subjects that borrow a ministry subject code for ranking data. Final Word delivery defaults to the ministry first-level subject basis, so the release gate expects one report per unique ministry subject/code rather than one report per proxy request row.

If a future delivery explicitly needs one report per coverage row, set `REPORT_BASIS = "coverage_subject"` in `scripts/audit_release_quality_gate.py` and regenerate reports with subject-level requests instead of code-only batching.

## Stable Boundaries

- `data/` is raw source input and should not be overwritten.
- `processed/` is generated structured data. SQLite is the preferred query interface.
- `configs/runtime/` contains request, source, proxy, and mapping policy.
- `configs/runtime/ranking_source_inputs.json` selects the preferred version and compatible sheet for consolidated ranking sources such as ARWU.
- `outputs/subject_agent_runs/` contains per-subject artifact runs.
- `outputs/full_word_reports/` contains final Word outputs and QA render artifacts.

## Known Technical Debt

- Some legacy scripts are math-only prototypes and are registered in `configs/runtime/legacy_script_registry.json`.
- `subject_artifact_builders.py` and `build_word_replacement_trial.py` are large and should be split by artifact family and Word assembly responsibility.
- Several historical docs contain encoding damage. Prefer this file plus `DATA_CONTRACT.md` and `REPORT_QA.md` for handoff.
