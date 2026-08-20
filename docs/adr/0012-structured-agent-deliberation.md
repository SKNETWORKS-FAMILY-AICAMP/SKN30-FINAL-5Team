# ADR-0012: 2라운드 구조화 Agent 상호검토

- 상태: ACCEPTED
- 날짜: 2026-08-20
- 소유자: 백엔드 개발팀장
- 승인자: 개발팀장 외 reviewer 1명 + 백엔드 owner + PM + 외부 도메인 검수자
- 관계: ADR-0007의 단일 proposal orchestration을 확장하며, 네 Agent·Coordinator·Safety 경계는 유지
- 관련 요구사항/이슈: `F002`, `F029`, `POL-008`, `NFR-003`, `NFR-006`, `TASK-AGENT-002`

## 배경

ADR-0007은 Training·Recovery·Safety·Feasibility 네 Agent가 동일한 정규화 입력과 승인 후보로
구조화 proposal을 병렬 생성하고, 결정적 Coordinator가 최종 추천 하나를 선택하도록 확정했다.
현재 구현은 이 계약과 fail-closed, Safety veto, 재현성 요구를 충족하지만 각 Agent는 다른
Agent의 proposal을 보지 않고 한 번만 판단한다.

사용자에게 역할별 요약을 나열하는 것만으로는 회복 상한, 안전 제외, 장비 제약과 목표 보존이
어떻게 조정됐는지 충분히 설명하기 어렵다. 반대로 LLM Agent들이 자유 텍스트로 서로 설득하면
결과 drift, Safety 희석, hidden reasoning 노출, 감사 불가능성과 외부 provider 장애가 결정 경로에
들어온다.

따라서 기존 결정적 core를 유지하면서 서로의 구조화 constraint와 preference만 한 번 검토하는
bounded deliberation 계약이 필요하다.

## 결정

이 ADR은 다음 V2 목표 구조를 채택한다. A2 기준 구현과 필수 검증이 병합되기 전까지 활성
production 기준은 ADR-0007의 현재 V1 흐름이다.

### 1. 실행 단계

1. **Round 1 — independent proposal**
   - 네 필수 Agent가 동일한 immutable request와 승인 후보를 받는다.
   - 누락·`FAILED`는 decision `FAILED`, `NEEDS_INPUT`은 계획 없는 `NEEDS_INPUT`으로 종료한다.
2. **Deterministic conflict detection**
   - 검증된 proposal·후보·버전 정책만 입력으로 사용한다.
   - conflict code와 review 대상 Agent를 canonical order로 만든다.
   - conflict가 없으면 Agent를 다시 호출하지 않고 Round 2 상태를 `SKIPPED_NO_CONFLICT`로 기록하며,
     네 Agent 모두 `NOT_REQUIRED` event를 남긴다.
3. **Round 2 — structured review**
   - 영향받는 Agent만 다른 Agent의 구조화 proposal hash·constraint·preference를 검토한다.
   - 비대상 Agent는 `NOT_REQUIRED` review event를 남긴다.
   - 대상 review 누락·`FAILED`는 decision `FAILED`, `NEEDS_INPUT`은 계획 없는 `NEEDS_INPUT`이다.
   - 최대 한 번만 실행하며 추가 토론 루프를 만들지 않는다.
4. **Integrity validation and deterministic Coordinator**
   - Round 1 대비 hard constraint 단조성과 전역 불변식을 검증한다.
   - 미해결 충돌은 아래 권한 계약으로 해소하며 안전하고 실행 가능한 후보가 없으면 계획을 만들지 않는다.
   - 독립적인 FinalSafetyGate를 추가하지 않는다.
5. **Public narration**
   - 확정된 결과와 공개 가능한 review code에서 템플릿 설명을 만든다.
   - 선택적 LLM은 한 번의 bounded batch로 일반 문장 slot만 바꿀 수 있다.

### 2. 권한과 변경 가능 범위

모든 Agent는 승인 후보를 제한하거나 선호할 수 있지만 새 운동을 만들 수 없다.

| 권한 | 불변 hard constraint | 조정 가능한 preference |
|---|---|---|
| 전역 | 요청 시간, 시간 출처, 승인 후보 집합, 입력·정책·카탈로그·규칙 버전 | 없음 |
| Safety | `BLOCKED`, `REST`, `STOP_AND_SEEK_HELP`, veto, 제외 운동, 승인 안전 규칙 | 승인된 대체 후보 중 선호 |
| Feasibility | 현재 장소·장비·가용 시간으로 불가능한 후보 | 가능한 대체 후보·순서 |
| Recovery | 승인 정책이 만든 최대 강도·부하·볼륨·복귀 상한 | 상한 안의 회복 구성 |
| Training | 사용자 primary goal과 승인된 최소 목표 조건 | 상위 hard constraint 안의 운동 종류·구성 |

Safety Agent만 veto를 `false -> true`로 강화하거나 제외 운동을 추가할 수 있다. Feasibility 불가능과
Recovery 상한은 다른 Agent의 선호로 해제할 수 없다. Training 목표를 위의 hard constraint와
동시에 보존할 수 없으면 다른 목표로 바꾸거나 시간을 줄이지 않고 기존 계약의 계획 없는 상태로
종료한다.

### 3. 내부 구조화 계약

Round 1은 기존 `AgentProposal`을 schema `0.2.x`로 확장할 수 있다. 상세 필드는 A2에서 Pydantic으로
구현하되 다음 의미를 고정한다.

- `hard_constraint_codes`: 다른 Agent가 완화할 수 없는 제약
- `preference_codes`: hard constraint 안에서 조정 가능한 선호
- `preferred_exercise_ids`, `excluded_exercise_ids`: 승인 공통 후보 안의 ID만 허용
- `evidence_reference_codes`: 저장된 최소 입력·규칙의 machine reference
- `policy_version`: proposal을 만든 승인 정책 버전

Round 2의 `AgentReview`는 최소 다음을 가진다.

- `review_schema_version`, `round_number=2`, `agent_type_code`
- `review_status_code`: `READY | NOT_REQUIRED | NEEDS_INPUT | FAILED`
- `revision_status_code`: `UNCHANGED | REVISED | NOT_REQUIRED | null`. `NEEDS_INPUT`·`FAILED`에는 null
- `baseline_proposal_hash`, canonical `(agent_type_code, proposal_hash)` 구조의
  `reviewed_proposal_references`
- `reviewed_agent_types`
- `accepted_constraint_codes`, `unresolved_conflict_codes`
- `revision_reason_codes`, `evidence_reference_codes`
- `revised_proposal`: `REVISED`일 때만 존재하는 검증된 proposal

hash와 tuple/list는 canonical order를 사용한다. 자유 텍스트 reasoning과 provider 예외 문자열은
proposal·review에 포함하지 않는다.

### 4. conflict와 종료 계약

conflict code namespace는 버전화하며 최소 다음 범주를 가진다.

- Training preference와 Safety 제외 충돌
- Training/후보 부하와 Recovery 상한 충돌
- Safety 대체 후보와 Feasibility 장소·장비 충돌
- 요청 시간 불일치
- primary goal 미보존
- 안전하고 실행 가능한 승인 후보 없음

미해결 conflict를 해결할 때 Safety hard constraint, 전역 사용자 제약, Feasibility hard constraint,
Recovery ceiling, Training goal, 일반 preference 순으로 **검증**한다. 이 순서는 상위 제약을 낮은
제약으로 덮어쓰는 가중치가 아니다. 모든 필수 hard constraint를 만족하는 후보만 성공할 수 있다.

### 5. 재현성과 저장

동일한 입력 snapshot, 후보, Round 1 proposal, conflict/precedence, Round 2 review와 모든 관련
버전은 동일한 final action과 candidate를 만들어야 한다. 최소 저장 요구는 다음과 같다.

- V1과 구분되는 `graph_version`(구현 시 새 버전 부여)
- Round 1 proposal과 canonical hash
- conflict detector·precedence version과 conflict code
- Round 2 대상, `NOT_REQUIRED` 포함 review event, revised proposal과 hash
- Coordinator version과 final result
- 공개 narration의 template/prompt/model/fallback version

기존 decision·proposal·final result를 파괴적으로 변경하지 않고 additive persistence를 사용한다.
구체 SQLAlchemy 모델과 migration은 백엔드 owner의 별도 task와 승인을 거친다.

### 6. LLM과 Agent Tool 경계

Agent와 conflict detector는 LLM, DB, FastAPI, ORM, 외부 SDK를 직접 호출하지 않는다. application
service가 정규화·버전화된 tool/port 결과를 immutable request로 조립한다. Tool은 승인된 catalog,
goal/routine policy, recovery ceiling, Safety rule/alternative, duration, 장소·장비 호환성과 같은
결정적 기능만 제공한다.

LLM은 최종 결정 이후 machine code, 정수, 불리언, null로만 구성된 공개 allowlist payload를 받아
일반 narration slot을 변환할 수 있다. application log, 직접 식별자, 날짜, 자유 체크인, 원시 건강·
웨어러블 값, hidden reasoning과 graph checkpoint는 보내지 않는다. safety status가 `PASS/REVISE`가
아니거나 최종 action이 `REST/STOP_AND_SEEK_HELP`이거나 Safety veto가 있는 결과는 기존 검수
템플릿만 사용한다.

### 7. LangGraph 도입 게이트

A2 기준 구현은 framework-independent Python/Pydantic domain core로 만든다. LangGraph는 다음을
모두 확인한 별도 PoC·ADR 전에는 production dependency로 추가하지 않는다.

- 기준 구현과 동일한 golden·reproducibility·Safety 결과
- 중단·재개, streaming, human-in-the-loop 또는 세 개 이상의 조건부 분기라는 실제 필요
- 현재 PostgreSQL 원자적 decision 저장과 checkpointer 중복 방지
- checkpoint 최소화·암호화·보존·삭제 계약
- 허용 가능한 latency, failure surface와 운영 복잡도

LangGraph를 채택해도 orchestration만 담당하며 domain Agent, conflict detector와 Coordinator는
framework-independent하게 유지한다.

## 결정 이유

- 독립 평가의 역할 분리와 상호검토의 설명 가능성을 함께 확보한다.
- hard constraint와 preference를 분리해 Safety가 다른 Agent에게 설득되는 경로를 차단한다.
- conflict가 있을 때만 한 번 review해 무제한 토론과 불필요한 지연을 막는다.
- LLM을 결정 경로 밖에 둬 provider 장애 시에도 동일한 계획을 반환한다.
- 프레임워크보다 domain 계약을 먼저 검증해 현재 모듈형 모놀리스와 재현성 저장을 보존한다.

## 검토한 대안

- 현재 단일 proposal + Coordinator 유지
- 네 Agent가 항상 두 번째 proposal을 제출
- LLM Agent의 자유 형식 다중 라운드 토론
- 처음부터 LangGraph + persistent checkpointer 도입
- Coordinator 뒤 독립 FinalSafetyGate 재도입

## 선택하지 않은 대안과 이유

- 현재 구조만 유지하면 다른 전문 제약의 수용·충돌·수정 이력을 표현하기 어렵다.
- conflict가 없어도 항상 재실행하면 결과 정보 없이 지연과 장애 지점만 늘어난다.
- 자유 형식 LLM 토론은 결정 drift, Safety 희석, 재현 실패와 개인정보 전송 위험이 있다.
- 초기 LangGraph persistence는 기존 decision 저장과 중복되고 필요성이 측정되지 않았다.
- FinalSafetyGate는 ADR-0007이 제거한 중복 안전 결정과 불일치 위험을 다시 만든다.

## 결과와 영향

- ADR-0007의 네 Agent, 결정적 Coordinator, 독립 FinalSafetyGate 없음은 유지한다.
- 승인 시 ADR-0007의 "네 proposal 뒤 즉시 Coordinator" orchestration만 본 ADR의 bounded
  deliberation으로 확장한다.
- A1은 문서·계약만 변경하며 production 동작, API와 DB schema는 바꾸지 않는다.
- A2 domain core, A3 비교 검증, B2 persistence, B3 API, A4 narration, A5 LangGraph 평가로 분리한다.

## 보안·개인정보·호환성 영향

- review 입력은 기존 식별자 제거 snapshot과 구조화 proposal로 제한한다.
- review·conflict·narration은 계정 삭제 시 decision과 함께 삭제하며 별도 장기 기억으로 쓰지 않는다.
- application log와 LangGraph checkpoint를 사용자용 Agent 로그로 재사용하지 않는다.
- 공개 API 변경은 additive optional 필드와 frontend compatibility test가 있는 별도 승인 대상이다.
- 새로운 안전 수치나 규칙은 본 ADR로 승인하지 않는다.

## 아직 확정되지 않은 사항

- A2 Pydantic class·enum의 정확한 이름과 `0.2.x` patch version
- conflict code 전체 목록과 정책별 Recovery ceiling 데이터
- additive DB 테이블의 물리 컬럼·인덱스·보존 구현
- 공개 deliberation event의 API 필드명과 화면 표현
- 기준 구현 결과에 따른 LangGraph 채택 여부

## 후속 작업

1. A2에서 framework-independent domain core와 단위 테스트를 구현한다.
2. A3에서 V1/V2 golden, Safety invariant, replay, latency를 비교한다.
3. 백엔드 owner가 additive persistence와 migration을 구현한다.
4. 공개 API·프론트 호환성을 별도 task에서 승인한다.
5. 기존 narration adapter를 code-only single-batch deliberation 문구로 확장한다.
6. 기준 구현에서 필요성이 확인된 경우에만 LangGraph PoC와 후속 ADR을 진행한다.
