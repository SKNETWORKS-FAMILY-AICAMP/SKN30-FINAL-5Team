# Decisions module

Wave 6 implementation lives in this module. `DecisionContextAssembler` creates the minimum
versioned input, four deterministic proposal agents run through the shared parallel runner, and
`DecisionService` coordinates idempotency and the transaction boundary. The module never calls an
LLM. Wave 7 selection and workout-session creation are delegated to the workouts application
service so this module remains focused on decision creation and replay.

입력 snapshot, 공통 기본 candidate, Training·Recovery·Safety·Feasibility proposal, Coordinator의 Safety 의견 반영, 최종 결정의 원자적 저장을 orchestration합니다. 독립적인 최종 Safety 재검사는 수행하지 않습니다.
