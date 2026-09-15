# ADR-0026: Single draft with parallel critics experiment

- Status: ACCEPTED
- Date: 2026-09-15
- Owner: AI/data lead
- Approval: project owner approved starting architecture E on 2026-09-15
- Related: ADR-0015, ADR-0025

## Context

B generated valid plans more reliably than C, while D's requirement to generate two valid
candidates made complex and conflict cases fail before deliberation. Multi-agent value has
not appeared as reliably better plan generation, but one D run demonstrated useful reviewer
disagreement and a bounded selection change.

## Decision

Evaluate architecture E, `SINGLE_DRAFT_PARALLEL_CRITICS`:

1. Reuse B's Single-Agent+RAG generator to produce one complete draft.
2. Compile and validate the draft before any critic call.
3. Recovery and Feasibility review only that valid draft, in parallel, and return typed,
   monotone patch proposals rather than plans.
4. Coordinator may accept or reject submitted patch IDs but cannot emit prescriptions.
5. The server applies accepted patches and runs the common compiler and integrity validator.
6. Any critic, Coordinator, patch, or post-patch validation failure preserves the already
   valid original draft. Only failure to obtain the original draft reaches deterministic
   fallback.
7. Equipment ownership is not a generation, review, or selection condition.

## Experiment boundary

Only `backend/tests/evaluation/**`, evaluation results, and documentation change. Public API,
database schema, production LangGraph, safety policy, and production prompts remain unchanged.

## Acceptance criteria

- Reviewers cannot add, remove, replace, or reorder exercises.
- Coordinator cannot invent a patch or rewrite a prescription.
- Invalid or conflicting patches cannot alter the original draft.
- A critic or Coordinator failure still delivers the valid original direct plan.
- Safety exclusions and the duration window remain enforced downstream.
- B and E can be evaluated from the same initial draft so quality differences isolate review
  value rather than generation variance.

