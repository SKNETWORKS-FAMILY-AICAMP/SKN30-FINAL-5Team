# TASK-MULTI-AGENT-SINGLE-DRAFT-CRITICS-EXPERIMENT

## Objective

Prototype and evaluate architecture E: one validated B-equivalent draft, parallel Recovery
and Feasibility critics, and server-applied bounded patches selected by a non-rewriting
Coordinator.

## Files expected to change

- `backend/tests/evaluation/single_draft_review.py`
- `backend/tests/evaluation/single_draft_review_provider.py`
- `backend/tests/evaluation/runners/single_draft_review.py`
- focused evaluation tests and CLI
- this task, ADR-0026, and experiment results

## Risks

- API/DB: none; evaluation-only.
- Safety: a patch could weaken a valid draft; monotone patch contracts and the final existing
  validator must reject it.
- Compatibility: E must not change A/B/C defaults or their stored historical results.
- Measurement: shared draft identity must be retained so B-vs-E quality isolates critic value.
- Privacy: critics receive normalized constraints and only catalog data for prescribed
  exercises; no direct identifiers or raw wearable records.

## Plan

1. Add hashed review, patch-decision, and materialization contracts.
2. Add provider adapters with minimal role-specific payloads.
3. Compose B draft generation, parallel critics, bounded selection, and original-draft
   preservation in an evaluation runner.
4. Verify no-change, valid patch, invented/conflicting patch, critic failure, Coordinator
   failure, and downstream safety/duration rejection.
5. Add zero-cost dry-run/offline comparison before any paid pilot.

