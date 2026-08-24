# TASK-AGENT-003: Safety-first LLM 멀티에이전트 V3 계약

- Primary owner: AI/data lead
- Reviewers: 개발팀장, 백엔드 owner, PM, 외부 도메인 검수자, 프론트엔드 owner
- 관련 요구사항: `F002`, `F029`, `POL-008`, `NFR-003`, `NFR-006`
- 관련 ADR: `ADR-0007`, `ADR-0011`, `ADR-0012`, `ADR-0013`(`ACCEPTED`),
  `ADR-0014`(`ACCEPTED`)
- 목표 브랜치: `docs/TASK-AGENT-003-vector-contracts`
- 현재 상태: `IN_PROGRESS`

상태 정합성: ADR-0013과 ADR-0014는 2026-08-24 `ACCEPTED`되었고 V3 목표 계약과 Qdrant retrieval
경계를 승인한다. 공통 retrieval domain contract 구현에 착수했지만 Qdrant adapter·migration·LLM graph,
shadow 검증과 production 전환은 완료되지 않았다.

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
- PostgreSQL deterministic eligible/mandatory filter 뒤 Qdrant ranking과 PostgreSQL 재검증을 수행하는
  `ExerciseRetriever`/`ExercisePoolSnapshot V3` 문서 계약
- Vector 장애·stale/version mismatch의 deterministic pool fallback과 canonical failure code
- 온보딩 `PainAreaInput`, `pain_present` 정합성, versioned 1..10 severity mapping 목표 계약
- difficulty-only workout feedback과 legacy field deprecation/weekly pain 집계 전환 계약
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
- 문서 제안의 필수 승인 전 새로운 통증 임계값 production 활성화, 안전 규칙·운동 처방 수치 변경
  또는 미검수 운동 승인
- LLM의 Safety veto 생성·완화, 자유 형식 운동 생성, raw SQL/ORM 접근
- LangGraph persistent checkpointer와 장기 Agent memory
- Qdrant client/production adapter, collection/embedding build와 dependency
- 물리 DB schema/migration, public OpenAPI/Pydantic/frontend 구현

## 인수 조건

1. V1 production, 승인된 V2 목표, `ACCEPTED`지만 미구현인 V3 목표를 문서에서 구분한다.
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
17. PostgreSQL에서 eligible/mandatory exercise ID를 먼저 결정하고 Qdrant는 그 범위 안의 순위와
    다양성만 결정한다. 반환 ID는 같은 catalog version의 PostgreSQL에서 다시 검증한다.
18. mandatory 목표 운동과 승인 안전 대체는 Vector 결과에 없어도 snapshot에 보존된다.
19. Qdrant unavailable/not-ready/timeout/stale/index-version mismatch는 결정적 pool fallback으로 처리하고
    Safety 결과를 바꾸지 않는다.
20. `ExerciseRetrievalRequest/Result`, `exercise-pool-snapshot-v3`, graph retrieval field, collection/index/
    embedding/query/fallback version과 canonical retrieval code가 문서에서 일치한다.
21. 온보딩은 `pain_present`와 부위별 1..10 점수를 사용하고 false/empty, true/non-empty, duplicate 금지,
    `OTHER` 저장 금지와 모든 점수 필수 검증을 정의한다.
22. `pain-intensity-map-v1`의 1..3 MILD, 4..6 MODERATE, 7..10 SEVERE 제안은 필수 안전 승인 전
    production에 적용하지 않고 기존 attention data에서 점수를 추정하지 않는다.
23. 신규 workout feedback은 difficulty 하나이며 기존 field/column을 즉시 삭제하지 않는다. 운동 중
    Safety Event API를 유지하고 `pain_report_count`의 versioned 집계 원천을 정의한다.
24. 통증 부위·점수는 Qdrant vector/payload/embedding query에 포함하지 않는다.

## 변경 예상 파일

- `docs/tasks/TASK-AGENT-003.md`
- `docs/adr/0007-multi-agent-structure-correction.md`
- `docs/adr/0012-structured-agent-deliberation.md`
- `docs/adr/0013-safety-first-llm-multi-agent.md`
- `docs/adr/0014-qdrant-exercise-pool-vector-retrieval.md`
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
- 후속 additive onboarding pain pair와 difficulty-only feedback 요청 계약. 현재 public schema는 이번
  단계에서 변경하지 않고 legacy field를 양쪽 지원 후 deprecated하는 순서를 사용
- 기존 V1/V2 response와 historical `SAFETY` summary는 계속 조회 가능
- V3 safety summary는 `SafetyPolicyEngine`의 공개 가능한 code projection이며 LLM Agent proposal이 아님

## DB·마이그레이션 영향

이번 task는 논리 계약만 정하며 migration은 만들지 않는다. 후속 persistence task는 기존 테이블을
파괴적으로 변경하지 않고 `decision_constraint_envelopes`, `decision_exercise_pools`,
`decision_coordination_attempts`, `plan_integrity_validations`와 regeneration lineage를 additive하게
도입한다. `agent_proposals`의 model/prompt/output schema metadata 확장과 V1/V2 historical row
호환 전략을 포함해야 한다.

ADR-0014에 따른 후속 persistence task는 `vector_index_registry`, `decision_exercise_retrievals`와
`decision_exercise_pools` retrieval metadata를 additive하게 도입한다. 온보딩 점수는 별도
`user_onboarding_pain_areas` 논리 모델을 검토하고 legacy attention/feedback row를 rewrite하지 않는다.

## 안전·개인정보·보안 영향

- Safety veto와 `STOP_AND_SEEK_HELP`는 LLM 호출 전에 확정하며 모든 이후 단계가 완화할 수 없다.
- 최종 검증은 앞단 안전 분류를 재해석하지 않고 저장된 constraint 준수만 확인한다.
- Agent는 식별자 제거 snapshot과 승인 운동 pool만 받는다.
- LLM은 DB Tool, raw SQL, ORM, application log와 원시 provider payload를 받지 않는다.
- 재생성은 Safety constraint를 약화하거나 안전한 대안이 없을 때 차이를 억지로 만들지 않는다.
- 통증 부위·점수, 직접 식별자와 raw health/wearable data를 Qdrant payload/vector/embedding query에
  포함하지 않는다.

## 선행 관계와 차단 요소

- ADR-0013은 `ACCEPTED`지만 구현·검증과 production 전환 승인은 별도다.
- ADR-0014 필수 승인은 완료됐다. 별도 안전 계약인 `pain-intensity-map-v1`은 개발팀장·PM·외부 도메인
  검수 승인이 필요하다.
- `backend/app/domain/agents/AGENTS.md`는 V1/V2 production과 승인된 V3 목표를 구분하도록 갱신했다.
  production Agent 구현은 이 문서의 구조화 출력·결정적 Safety/fallback 경계를 계속 준수한다.
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
- Safety 차단 시 Qdrant zero-call, eligible 밖 ID 제거와 PostgreSQL 재검증
- mandatory 운동 보존, Qdrant 장애·stale/version mismatch의 deterministic fallback과 stable hash
- collection/catalog/index/embedding/graph/prompt/model version lineage와 stored retrieval replay
- onboarding pain 정합성·중복·OTHER·1..10 경계와 versioned severity mapping
- difficulty-only/legacy feedback 양쪽 지원, historical row 보존과 pain report 중복 제거 집계

## 수동 확인

1. `rg -n "ADR-0013|LLM 멀티에이전트 V3|SafetyPolicyEngine" docs`
2. `rg -n "LangChain|LangGraph|ExercisePoolSnapshot|RegenerationContext" docs`
3. `git diff --check`
4. V1/V2 production을 구현 완료로 유지하면서 V3 목표 승인과 V3 production 구현 완료를 구분했는지
   확인한다.

## 알려진 제한과 후속 작업

- V3-A2: Pydantic domain contract와 LangChain Agent adapter 구현
- V3-A3: LangGraph orchestration, timeout, repair와 deterministic fallback 구현
- V3-B1: additive persistence와 Alembic migration
- V3-B2: regeneration API와 frontend compatibility 구현
- V3-C1: shadow evaluation, golden, expert review, latency·cost·fallback 측정
- V3-C2: 기준 충족 후 ADR-0013에 따른 production graph 전환 승인 검토
