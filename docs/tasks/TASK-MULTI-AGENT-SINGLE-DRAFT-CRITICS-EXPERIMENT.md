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

## Progress (2026-09-15)

The contracts, provider adapter, shared-draft runner, and cost-gated CLI are implemented.
Focused checks cover no-change, valid patch, critic failure, invented Coordinator patch,
post-patch duration failure, and one-time shared draft generation. Ruff, mypy, strict OpenAI
schema binding, and the full evaluation suite passed before the first paid run.

The first three-case paid run preserved B's 3/3 direct-plan rate but made no accepted changes.
Two cases completed with `NO_CHANGE`; one critic failed and the valid original was retained.
Inspection found that the critic payload lacked the normalized constraint envelope. The
adapter now includes the existing privacy projection so critics can see goal, duration,
location, recovery ceiling, and safety exclusions. Equipment ownership remains deliberately
excluded. See `results/single-draft-review-pilot/README.md`.
