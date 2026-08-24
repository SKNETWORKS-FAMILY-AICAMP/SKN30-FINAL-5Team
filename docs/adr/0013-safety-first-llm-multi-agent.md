# ADR-0013: Safety-first LangGraph LLM 멀티에이전트 루틴 합성

- 상태: ACCEPTED
- 날짜: 2026-08-24
- 소유자: AI/data lead
- 승인자: 개발팀장 + 백엔드 owner + PM + 외부 도메인 검수자 + 프론트엔드 owner(API)
- 관계: 승인 시 ADR-0007의 네 proposal·결정적 Coordinator 구조와 ADR-0012의 narration-only·
  LangGraph 보류 결정을 대체하고, ADR-0011의 안전 문구·provider adapter 경계는 유지
- 관련 요구사항/이슈: `F002`, `F029`, `POL-008`, `NFR-003`, `NFR-006`, `TASK-AGENT-003`

## 배경

현재 production 기준은 Training·Recovery·Safety·Feasibility 네 결정적 proposal과 결정적
Coordinator다. ADR-0012는 결정적 conflict detection과 한 번의 구조화 review를 승인했지만 LLM을
최종 narration에만 허용한다. 이 구조는 안전·재현성에는 강하지만 실제 proposal과 루틴 구성이 규칙
분기로만 이루어져 LLM 기반 agentic 협업으로 설명하기 어렵다.

제품은 통증·이상 반응, 요청 시간, 장소·장비와 검수 카탈로그를 다루므로 LLM이 자유 형식으로 안전
기준이나 운동을 만들게 할 수 없다. 반대로 완성된 결정적 후보만 LLM이 고르면 핵심 루틴 생성은 여전히
규칙 엔진에 남는다. 따라서 결정적 정책은 안전한 생성 공간을 만들고, LLM Agent는 그 공간 안에서
구조화 루틴 proposal을 만들며, 결정적 compiler와 validator가 실행 가능성을 보장하는 경계가 필요하다.

확정한 V3에는 병렬 Agent, 조건부 review, Coordinator repair, 수동 재생성 재진입이 있어 명시적
상태·분기·반복을 관리하는 orchestration runtime이 필요하다.

## 결정

이 ADR은 승인·구현 전까지 production 기준을 바꾸지 않는 V3 목표 계약이다.

### 1. Safety-first 실행 순서

1. application loader가 사용자 소유 데이터를 repository로 읽고 식별자를 제거한 immutable input
   snapshot을 만든다.
2. 결정적 `SafetyPolicyEngine`이 LLM 호출 전에 `REST`, `STOP_AND_SEEK_HELP`, 생성 허용 여부,
   veto, 제외 운동, 강도·부하 상한과 안전 대체 범위를 결정한다.
3. 결정적 constraint builder가 Safety 결과, 요청 시간, 목표, 장소·장비, recovery 정책과 version을
   `ConstraintEnvelope`로 고정한다.
4. application loader는 동일 catalog version에서 production-approved 운동을 방식 A로 사전 조회하고
   canonical `ExercisePoolSnapshot`과 hash를 만든다.
5. Training·Recovery·Feasibility 세 LLM Agent가 동일한 envelope와 pool을 받아 병렬 proposal을
   만든다.
6. 결정적 conflict detector가 proposal 상호 간 및 envelope 위반을 canonical code로 만든다.
7. 충돌이 있을 때만 영향 Agent를 한 번 병렬 재검토하며 hard constraint를 완화하지 않는다.
8. LLM Coordinator는 세 proposal과 review를 종합·선택해 하나의 구조화 `PlanSpec`을 반환한다.
9. 결정적 Plan Compiler가 `PlanSpec`을 실행 블록으로 만들고, 최종 integrity validator가 저장된
   envelope의 안전·시간·목표·장비·스키마 제약 준수와 승인 운동 참조를 검사한다.
10. repairable violation은 code로 Coordinator에 한 번만 돌려보낸다. 재실패 또는 non-repairable
    violation은 결정적 fallback 또는 계획 없는 상태로 종료한다.

### 2. Agent와 결정적 컴포넌트 권한

| 구성요소 | 권한 | 금지 |
|---|---|---|
| SafetyPolicyEngine | veto, 생성 금지, 제외, 상한, REST/중단 결정 | LLM 호출, 자유 추론 문구 |
| Training LLM Agent | 승인 pool 안에서 목표 보존 루틴 초안 생성 | 미승인 운동, 시간·안전 상한 변경 |
| Recovery LLM Agent | 승인 recovery ceiling 안의 부하·휴식·구성 제안 | ceiling 완화·초과 |
| Feasibility LLM Agent | 장소·장비·시간 안의 실행 가능성·구성 제안 | 불가능 조건 해제 |
| Conflict detector | canonical 충돌과 review 대상 계산 | LLM 호출, 충돌 임의 해소 |
| Coordinator LLM Agent | proposal·review 종합·선택, repair 가능한 PlanSpec 수정 | Safety·시간·목표·pool 완화, DB 조회 |
| Plan Compiler | 시간 산술, block canonicalization, catalog reference 연결 | 의료 판단, 새 운동 선택 |
| Integrity validator | 최종 plan의 envelope 준수 assertion | 원시 상태 재분류, constraint 변경 |

Safety는 Agent로 세지 않는다. V3의 LLM Agent는 Training·Recovery·Feasibility와 Coordinator이며,
공개 안전 요약은 SafetyPolicyEngine 결과의 검수된 projection이다.

### 3. LangChain과 LangGraph

- LangChain은 provider adapter, role prompt, allowlisted tool, Pydantic structured output과 schema error
  handling에 사용한다.
- LangGraph는 immutable typed state, 세 Agent fan-out/fan-in, conditional review, Coordinator repair,
  fallback과 regeneration routing에 사용한다.
- LangGraph node는 domain 함수를 호출할 뿐 Safety, conflict, compiler, validator 규칙을 소유하지 않는다.
- PostgreSQL이 canonical decision source of truth다. 동기 V3 첫 구현은 persistent LangGraph
  checkpointer를 사용하지 않으며, 재시작과 재생성은 저장된 decision record를 loader node가 읽어
  새 graph invocation을 만든다.
- persistent checkpoint 필요가 측정되면 직접 식별자 제거, 암호화, retention, account deletion,
  PostgreSQL 중복 방지 계약을 별도 ADR로 승인한다.

### 4. DB와 Tool 경계 — 방식 A

Agent와 Coordinator는 DB, repository, ORM, raw SQL을 직접 호출하지 않는다. application loader가
프로필·체크인·수행 이력·선호·이전 plan과 승인 catalog를 읽고 최소화·버전화된 snapshot을 graph
state에 넣는다.

Training Agent도 초기 V3에서는 DB 조회 Tool을 갖지 않는다. 승인 운동 pool이 prompt budget이나
품질 기준을 충족하지 못한다는 측정이 있을 때만 별도 승인으로 version-bound read-only catalog
Tool을 추가한다. Coordinator에는 DB Tool을 추가하지 않는다. duration estimate나 constraint check처럼
DB를 읽지 않는 순수 결정적 Tool만 허용할 수 있다.

### 5. 구조화 출력과 실패

Agent와 Coordinator 출력은 Pydantic schema, 승인 exercise ID, stable machine code, 정수, 불리언,
null과 짧은 공개 가능 summary로 제한한다. 자유 형식 plan, 새 exercise ID, prompt/chain-of-thought,
provider 예외 원문을 proposal에 넣지 않는다.

필수 LLM invocation은 timeout·schema invalid에 한 번의 bounded provider retry를 허용할 수 있다.
필수 Agent 하나라도 끝내 실패하면 부분 proposal로 Coordinator를 실행하지 않는다. 같은 envelope를
만족하는 현재 결정적 엔진의 fallback plan을 사용하고 최종 validator를 통과시킨다. 안전한 fallback이
없으면 원인에 따라 `REST`, `NEEDS_INPUT`, `FAILED` 또는 `STOP_AND_SEEK_HELP`로 종료한다.

### 6. Coordinator repair

다음 violation은 안전한 대체와 허용 범위가 있을 때만 repairable이다.

- 요청 시간 초과·미달
- 세트·반복 범위 초과
- Recovery ceiling 초과
- 운동 순서·스키마 오류
- 필수 목표 누락
- 장비 없는 운동 포함
- Safety 제외 운동 포함, 단 승인된 안전 대체가 존재

다음 상태는 Coordinator로 돌아가지 않는다.

- `STOP_AND_SEEK_HELP`
- Safety veto로 plan generation 금지
- 승인 안전 운동 없음
- 필수 사용자 입력 누락
- 정책·안전 ruleset 데이터 불완전
- Coordinator repair 후 같은 또는 다른 violation 재발
- LLM provider 전체 장애

Coordinator repair는 decision run당 최대 한 번이고 violation code와 attempt를 저장한다. validator를
우회해 성공으로 표시할 수 없다. `STOP_AND_SEEK_HELP`는 REST나 fallback plan으로 바꾸지 않는다.

### 7. 추가 입력 없는 수동 재생성

`POST /api/v1/decisions/{decision_id}/regenerations`는 유효한 input snapshot, ConstraintEnvelope와
ExercisePoolSnapshot을 재사용하고 세 전문 Agent부터 새 graph invocation을 실행한다. Coordinator만
재실행하지 않는다.

백엔드는 `RegenerationContext`에 generation mode, attempt, 이전 plan의 hash·exercise 순서·구조와
exact duplicate 금지 및 variation code를 자동으로 넣는다. 사용자는 상태나 사유를 다시 입력하지 않는다.

의미 있는 차이는 다음 중 하나 이상이다.

- 핵심 운동 하나 이상 변경
- 승인 범위 안의 세트·반복 구조 변경
- 루틴 구성 방식 변경

설명, UUID, 1초 휴식 같은 비의미 변경만으로는 통과하지 않는다. 안전하고 목표를 보존하는 대안이
없으면 constraint를 약화하지 않고 `NO_ALTERNATIVE_AVAILABLE`로 종료한다. root decision당 성공
재생성은 최대 두 번이며 각 mutation은 idempotent다.

snapshot/envelope/pool이 stale하거나 safety·catalog·policy version이 다르면 재생성하지 않고 새
decision/check-in 경로를 요구한다.

### 8. 재현성과 저장

LLM fresh inference가 byte-identical output을 보장한다고 가정하지 않는다. 대신 다음 저장 데이터로
provider 재호출 없이 final result를 replay해야 한다.

- 최소화 input snapshot과 hash
- ConstraintEnvelope, ExercisePoolSnapshot과 각 schema/version/hash
- graph, LangChain/LangGraph contract, prompt, model/provider version
- Round 1 structured proposal과 hash
- conflict, review 대상, review와 hash
- Coordinator initial/repair attempt와 structured output hash
- compiler version/result와 integrity validation codes
- deterministic fallback version과 사용 여부
- regeneration root/parent, sequence, previous/new plan hash와 variation result

hidden reasoning과 prompt 원문은 저장하지 않는다. 공개 가능 summary는 구조화 판단 code와 분리한다.

## 결정 이유

- Safety를 LLM 앞에 두고 이후 모든 구성요소가 완화할 수 없는 생성 경계를 만든다.
- 완성 후보 선택이 아니라 승인 운동 primitive 안의 실제 루틴 합성을 LLM Agent가 담당한다.
- 병렬 독립 proposal과 제한된 상호검토로 역할 분리와 협업을 모두 표현한다.
- LangGraph의 명시적 state·branch·bounded loop가 재검토, repair와 재생성 경로를 감사 가능하게 만든다.
- 방식 A의 frozen pool은 Agent별 DB query drift와 개인정보 노출을 줄이고 replay를 단순화한다.
- 최종 validator는 안전 규칙을 중복 실행하지 않고 실제 생성 plan이 확정 constraint를 지켰는지 확인한다.

## 검토한 대안

- 현재 결정적 네 Agent와 narration-only LLM 유지
- 완성된 결정적 후보를 LLM이 선택
- Safety LLM Agent를 다른 Agent와 병렬 실행
- Training Agent에 DB/catalog Tool을 처음부터 제공
- Agent가 순차적으로 이전 Agent plan을 덮어쓰기
- Coordinator부터 사용자 재생성
- 최종 검증 제거 또는 Safety만 검증
- LangChain 없이 provider SDK 직접 호출, 순수 Python orchestration 유지

## 선택하지 않은 대안과 이유

- 현재 구조와 완성 후보 선택은 LLM의 실질적 루틴 생성 책임이 약하다.
- Safety LLM Agent는 결정적 veto와 의료·안전 경계를 약화한다.
- 초기 DB Tool은 snapshot 불일치, 권한 확대, 장애와 replay 비용을 늘린다.
- 순차 덮어쓰기는 order bias와 누적 latency를 만든다.
- Coordinator는 종합·선택자이므로 같은 proposal만 다시 받아서는 의미 있는 재생성이 어렵다.
- 최종 검증 제거는 LLM/컴파일 결과의 constraint 위반을 놓치고 Safety-only 검증은 시간·장비·목표·
  schema 계약 위반을 놓친다.
- 현재 V3의 branch·review·repair·regeneration은 LangGraph 도입 필요를 충족한다.

## 결과와 영향

- 승인 시 SafetyAgent proposal은 V3에서 제거되고 결정적 SafetyPolicyEngine record로 대체된다.
- 전문 Agent 수는 세 개이며 Coordinator는 별도 LLM Agent다.
- LLM failure가 더 이상 항상 동일 plan을 뜻하지 않으며 결정적 fallback 사용 여부가 decision 결과에
  포함된다. Safety·시간·목표 hard constraint는 fallback에서도 동일하다.
- public API는 regeneration mutation과 optional generation metadata를 additive하게 확장한다.
- DB는 historical V1/V2 row를 보존하면서 V3 record를 additive하게 저장한다.
- 실제 dependency, migration, API와 runtime 구현은 별도 PR로 나눈다.

## 보안·개인정보·호환성 영향

- LLM payload는 식별자를 제거한 code, 승인 exercise metadata와 최소 요약으로 제한한다.
- raw health/wearable/calendar text, 위치 경로, 생년월일·나이, 이름·이메일을 전송하지 않는다.
- 사용자 범위 DB key는 loader 내부에만 있고 LLM input이나 Tool argument가 아니다.
- V1/V2 decision과 기존 `DecisionResponse`는 계속 조회 가능하다.
- historical `SAFETY` AgentSummary는 보존하되 V3 safety summary는 policy engine projection임을 API
  metadata와 문서에서 구분한다.
- graph state, provider error와 prompt를 application log에 쓰지 않는다.

## 아직 확정되지 않은 사항

- production model/provider code, temperature와 token budget
- ExercisePoolSnapshot 최대 운동 수와 prompt budget
- constraint·proposal·PlanSpec Pydantic의 정확한 patch version
- snapshot/envelope/pool freshness TTL
- meaningful difference의 운동 순서 거리와 최소 변경 세부 산식
- deterministic fallback이 현재 V1 전체를 재사용할지 축소 template plan을 사용할지
- latency·cost·expert evaluation의 production 승격 임계값

## 후속 작업

1. 필수 reviewer가 ADR-0013과 안전·API·DB 계약을 검토한다.
2. LangChain structured Agent와 pure domain contract를 구현한다.
3. LangGraph orchestration을 persistent checkpointer 없이 구현한다.
4. additive persistence와 migration, rollback/forward-fix를 구현한다.
5. regeneration API와 frontend compatibility를 구현한다.
6. V1 shadow 비교, golden·safety·privacy·replay·latency·cost 평가 후 production 전환을 승인한다.
