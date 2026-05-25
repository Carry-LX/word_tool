from __future__ import annotations

import json
from typing import Any


# Explicit variables. Keep ONLY_CODES empty to regenerate all unique ministry subject codes.
ONLY_CODES: list[str] = []

RUN_RENDER_QA = True
RUN_WORD_QA = True
RUN_SUBJECT_AGENT_FIRST = False
BUILD_NARRATIVE_BUNDLE = True
GENERATE_NARRATIVE_WITH_LLM = False
USE_DEMO_NARRATIVE_RESULT = False
UPDATE_WORD_FIELDS_WITH_COM = True


def apply_config(module: Any) -> None:
    module.ONLY_CODES = [code.zfill(4) for code in ONLY_CODES]
    module.RUN_RENDER_QA = RUN_RENDER_QA
    module.RUN_WORD_QA = RUN_WORD_QA
    module.RUN_SUBJECT_AGENT_FIRST = RUN_SUBJECT_AGENT_FIRST
    module.BUILD_NARRATIVE_BUNDLE = BUILD_NARRATIVE_BUNDLE
    module.GENERATE_NARRATIVE_WITH_LLM = GENERATE_NARRATIVE_WITH_LLM
    module.USE_DEMO_NARRATIVE_RESULT = USE_DEMO_NARRATIVE_RESULT
    module.UPDATE_WORD_FIELDS_WITH_COM = UPDATE_WORD_FIELDS_WITH_COM


def main() -> None:
    import regenerate_all_ministry_subject_word_reports as batch

    apply_config(batch)
    batch.main()


if __name__ == "__main__":
    main()
