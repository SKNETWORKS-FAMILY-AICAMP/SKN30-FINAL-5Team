# TASK-AGENT-003: Safety-first LLM 멀티에이전트 V3 계약

- Primary owner: AI/data lead
- Reviewers: 개발팀장, 백엔드 owner, PM, 외부 도메인 검수자, 프론트엔드 owner
- 관련 요구사항: `F002`, `F029`, `POL-008`, `NFR-003`, `NFR-006`
- 관련 ADR: `ADR-0007`, `ADR-0011`, `ADR-0012`, `ADR-0013`(`PROPOSED`)
- 목표 브랜치: `codex/llm-multi-agent-contracts`
- 현재 상태: `READY_FOR_REVIEW`

## 배경과 사용자 가치

현재 production 기준은 네 결정적 proposal과 결정적 Coordinator이며 LLM은 공개 narration만
담당한다. 역할은 분리됐지만 전문 Agent가 목표를 해석해 루틴을 구성하거나 다른 proposal을 반영해
재계획하지 않으므로 LLM 기반 agentic 협업으로 설명하기 어렵다.

V3는 결정적 Safety 경계를 유지하면서 Training·Recovery·Feasibility LLM Agent가 동일한 승인
운동 pool과 제약을 받아 병렬 proposal을 만들고, 충돌 시 영향 Agent만 한 번 재검토하며, LLM
Coordinator가 구조화 결과를 종합·선택하도록 한다. 사용자는 상태를 다시 입력하지 않고도 같은 안전
제약 안에서 의미 있게 다른 루틴을 최대 두 번 재생성할 수 있어야 한다.

## 포함 범위

- 결정적 `SafetyPolicyEngine`과 버전화된 `ConstraintEnvelope`
- 방식 A: application loader가 승인 운동을 사전 조회해 `ExercisePoolSnapshot`으로 고정
- Training·Recovery·Feasibility 세 LLM Agent의 LangChain structured output
- LangGraph 기반 병렬 fan-out/fan-in, 결정적 conflict detection, 조건부 Round 2 review
- 종합·선택자 역할의 LLM Coordinator와 최대 한 번의 구조화 repair
- 결정적 Plan Compiler와 최종 안전·정책 무결성 검사
- provider 장애·invalid output·수정 불가 오류의 결정적 fallback 또는 fail-closed 계약
- 추가 입력 없는 수동 재생성, 의미 있는 차이 검증, 최대 두 번 제한과 idempotency
- 공개 API의 additive regeneration 계약과 V1/V2 호환 전략
- PostgreSQL additive 논리 모델과 LangGraph checkpoint 경계
- V3 golden, safety, privacy, replay, regeneration, graph routing 테스트 계약

## 제외 범위

- `backend/app/**` production 구현
- LangChain·LangGraph dependency 추가와 `uv.lock` 변경
- SQLAlchemy model, repository, Alembic migration
- 프론트엔드 재생성 버튼 구현
- 새로운 통증 임계값, 안전 규칙, 운동 처방 수치 또는 미검수 운동 승인
- LLM의 Safety veto 생성·완화, 자유 형식 운동 생성, raw SQL/ORM 접근
- LangGraph persistent checkpointer와 장기 Agent memory

## 인수 조건

1. V1 production, 승인된 V2 목표, `PROPOSED` V3를 문서에서 구분한다.
2. Safety는 LLM Agent가 아니라 결정적 `SafetyPolicyEngine`이며 Agent 실행 전에 veto·제외·상한을
   포함한 immutable `ConstraintEnvelope`를 만든다.
3. application loader가 같은 catalog version에서 승인 운동을 canonical `ExercisePoolSnapshot`으로
   고정하며 Agent와 Coordinator는 DB·repository·ORM을 직접 호출하지 않는다.
4. Training·Recovery·Feasibility 세 Agent는 LangChain structured output으로 제한되고 동일한
   envelope와 pool을 받아 LangGraph에서 병렬 실행한다.
5. conflict detector와 review 대상 계산은 결정적이며 충돌이 있을 때만 영향 Agent를 최대 한 번
   재실행한다.
6. Coordinator는 세 proposal과 review를 종합·선택하며 새 안전 기준, 미승인 운동 또는 사용자 제약을
   만들거나 완화하지 않는다.
7. Plan Compiler는 구조화 PlanSpec을 실행 블록으로 컴파일하고 최종 validator는 원시 안전 판단을
   재실행하지 않고 envelope 준수만 검사한다.
8. repairable violation만 Coordinator에 machine code로 돌려보내고 repair는 최대 한 번이다.
   `STOP_AND_SEEK_HELP`, 생성 금지 veto, 안전 운동 없음, 필수 입력 누락, 정책 데이터 불완전,
   provider 전체 장애와 재실패는 Coordinator로 돌아가지 않는다.
9. provider 장애나 required Agent 실패 시 부분 proposal로 계속하지 않고, 같은 envelope를 만족하는
   결정적 fallback을 사용하거나 계획 없는 `FAILED`/`NEEDS_INPUT`/`REST`/`STOP_AND_SEEK_HELP`로
   종료한다.
10. 재생성은 유효한 기존 snapshot·envelope를 재사용하고 `RegenerationContext`를 추가해 세 Agent부터
    다시 실행한다. 정확히 같은 plan은 금지하며 핵심 운동, 순서, 세트·반복 또는 루틴 구조 중 하나
    이상의 의미 있는 차이를 검증한다.
11. stale snapshot·envelope, safety/catalog/policy version 불일치에서는 재생성을 실행하지 않고 새
    decision/check-in 경로를 요구한다. 성공 재생성은 root decision당 최대 두 번이다.
12. 공개 API는 기존 `DecisionResponse`를 깨지 않고 optional generation metadata와 별도 regeneration
    mutation을 additive하게 제안한다.
13. DB 논리 모델은 envelope, exercise pool, LLM invocation metadata, deliberation, coordination/repair,
    compilation/validation과 regeneration lineage를 별도로 저장한다.
14. LangGraph는 orchestration만 소유하고 PostgreSQL이 canonical decision source of truth다. V3 첫
    구현에는 persistent checkpointer를 사용하지 않는다.
15. 직접 식별자, 날짜, 자유 체크인, raw 건강·웨어러블 값, prompt 원문, chain-of-thought, provider
    예외 원문을 LLM payload·checkpoint·로그·공개 응답에 포함하지 않는다.
16. 저장된 envelope·pool·proposal·review·Coordinator output·compiler/validator 결과와 버전으로 provider
    재호출 없이 final result를 replay할 수 있어야 한다.

## 변경 예상 파일

- `docs/tasks/TASK-AGENT-003.md`
- `docs/adr/0007-multi-agent-structure-correction.md`
- `docs/adr/0012-structured-agent-deliberation.md`
- `docs/adr/0013-safety-first-llm-multi-agent.md`
- `docs/ARCHITECTURE.md`
- `docs/DOMAIN_RULES.md`
- `docs/API_CONTRACT.md`
- `docs/DATA_MODEL.md`
- `docs/TECHNICAL_PLAN.md`
- `docs/TEST_STRATEGY.md`
- `docs/TRACEABILITY.md`

## API 영향

- `POST /api/v1/decisions/{decision_id}/regenerations` additive mutation 제안
- `DecisionResponse`에 optional `generation_mode_code`, `root_decision_id`,
  `regeneration_sequence` 제안
- 기존 V1/V2 response와 historical `SAFETY` summary는 계속 조회 가능
- V3 safety summary는 `SafetyPolicyEngine`의 공개 가능한 code projection이며 LLM Agent proposal이 아님

## DB·마이그레이션 영향

이번 task는 논리 계약만 정하며 migration은 만들지 않는다. 후속 persistence task는 기존 테이블을
파괴적으로 변경하지 않고 `decision_constraint_envelopes`, `decision_exercise_pools`,
`decision_coordination_attempts`, `plan_integrity_validations`와 regeneration lineage를 additive하게
도입한다. `agent_proposals`의 model/prompt/output schema metadata 확장과 V1/V2 historical row
호환 전략을 포함해야 한다.

## 안전·개인정보·보안 영향

- Safety veto와 `STOP_AND_SEEK_HELP`는 LLM 호출 전에 확정하며 모든 이후 단계가 완화할 수 없다.
- 최종 검증은 앞단 안전 분류를 재해석하지 않고 저장된 constraint 준수만 확인한다.
- Agent는 식별자 제거 snapshot과 승인 운동 pool만 받는다.
- LLM은 DB Tool, raw SQL, ORM, application log와 원시 provider payload를 받지 않는다.
- 재생성은 Safety constraint를 약화하거나 안전한 대안이 없을 때 차이를 억지로 만들지 않는다.

## 선행 관계와 차단 요소

- ADR-0013이 필수 reviewer에게 `ACCEPTED`되기 전에는 V3가 production 계약이 아니다.
- 신규 LangChain·LangGraph dependency와 provider SDK는 별도 구현 PR에서 설명·검증한다.
- 새로운 안전 수치가 필요하면 별도 Safety task와 승인으로 분리한다.
- 공개 API와 DB migration은 프론트엔드·백엔드 owner의 별도 구현 승인이 필요하다.

## 테스트 계획

- Safety veto가 Agent·Coordinator·repair·재생성에서 완화되지 않는 불변식
- 세 Agent 병렬 fan-out/fan-in과 canonical result ordering
- structured output invalid·timeout·partial failure의 deterministic fallback
- conflict 유무별 Round 2 routing과 최대 한 번 review
- repairable/non-repairable violation routing과 Coordinator repair 최대 한 번
- 정확한 요청 시간, 승인 운동 pool, 목표, 장비·장소, Recovery ceiling 검증
- 재생성 exact duplicate 거부, 의미 있는 차이, 최대 두 번, stale envelope, idempotency
- provider 재호출 없는 stored-output replay
- DB migration additive/rollback 또는 forward-fix 및 historical V1/V2 조회 호환성
- LLM payload·로그·checkpoint에 직접 식별자와 원시 건강 데이터가 없는지 검증

## 수동 확인

1. `rg -n "ADR-0013|LLM 멀티에이전트 V3|SafetyPolicyEngine" docs`
2. `rg -n "LangChain|LangGraph|ExercisePoolSnapshot|RegenerationContext" docs`
3. `git diff --check`
4. V1/V2를 구현 완료로 유지하면서 V3를 승인·구현 완료로 오표기하지 않았는지 확인한다.

## 알려진 제한과 후속 작업

- V3-A2: Pydantic domain contract와 LangChain Agent adapter 구현
- V3-A3: LangGraph orchestration, timeout, repair와 deterministic fallback 구현
- V3-B1: additive persistence와 Alembic migration
- V3-B2: regeneration API와 frontend compatibility 구현
- V3-C1: shadow evaluation, golden, expert review, latency·cost·fallback 측정
- V3-C2: 기준 충족 후 ADR-0013 승인 상태와 production graph 전환 검토
