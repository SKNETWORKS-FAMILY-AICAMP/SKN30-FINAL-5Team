# Decisions module

Wave 6 implementation lives in this module. `DecisionContextAssembler` creates the minimum
versioned input, four deterministic proposal agents run through the shared parallel runner, and
`DecisionService` coordinates idempotency and the transaction boundary. Wave 7 selection and
workout-session creation are delegated to the workouts application service so this module remains
focused on decision creation and replay.

`explanations.py` owns public narration. It builds reviewed template sentences from approved codes
and may hand them to an optional narration provider, which can replace sentence text only. Action,
safety status, veto, candidates and reason codes always come from the Coordinator result, so an LLM
cannot change a decision. A vetoed, blocked, terminal-action, non-plan or non-shareable case never
reaches the provider, and any provider failure or rejected sentence falls back to the template.
The narration record is stored once per decision run with its source, template, prompt and model
version (ADR-0011).

입력 snapshot, 공통 기본 candidate, Training·Recovery·Safety·Feasibility proposal, Coordinator의 Safety 의견 반영, 최종 결정의 원자적 저장을 orchestration합니다. 독립적인 최종 Safety 재검사는 수행하지 않습니다.
