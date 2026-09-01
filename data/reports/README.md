# Operational catalog inputs

- `integrated_exercise_review_updated.csv`: final catalog generator input
- `representative_exercise_taxonomy_reviewed.csv`: reviewed representative taxonomy input
- `DB_LOAD_HANDOFF_STATUS.md`: DB 적재 전 1·2·3 완료 인계 상태와 적재 전 기술 확인

Collection, preprocessing, review, safety, and validation evidence is retained in
[`data/portfolio_evidence/`](../portfolio_evidence/README.md). The operational inputs
remain here because `build_exercise_catalog_v1.py` reads them directly.
