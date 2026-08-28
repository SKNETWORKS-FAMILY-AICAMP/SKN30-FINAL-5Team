# ADR-0015: V3 단일 라운드 에이전트 구성과 충돌·review 단계 제거

- 상태: ACCEPTED
- 날짜: 2026-08-28
- 소유자: AI/data lead
- 승인자: 채동현 (프로젝트 오너 겸 개발팀장 권한)
- 관계: ACCEPTED ADR-0013의 실행 순서 6·7단계와 conflict detector 권한을 대체한다.
  ADR-0012의 2라운드 상호검토는 어느 경로에서도 목표 계약이 아니므로 `SUPERSEDED`로 전환한다.
  ADR-0014의 retrieval 계약과 Safety-first 순서는 변경하지 않는다.
- 관련 요구사항/이슈: `F002`, `F029`, `POL-008`, `NFR-003`, `NFR-006`, 이슈 #175

## 배경

ADR-0013은 세 LLM Agent의 병렬 proposal 뒤에 결정적 conflict detector를 두고, 충돌이 있을 때만
영향 Agent를 한 번 재검토(round 2)한 후 LLM Coordinator가 종합하도록 정했다.

팀 검토에서 이 단계가 Coordinator의 역할과 중복되어 Coordinator의 책임이 흐려진다는 판단이 나왔다.
Coordinator의 정의된 임무는 "세 proposal을 종합·선택해 하나의 PlanSpec을 만드는 것"인데,
그 앞에 놓인 review 단계가 같은 일(제안 간 불일치 해소)을 먼저 시도한다.

구현 조사에서 다음이 확인됐다.

1. **제약 검사는 하류에서 이미 전부 재실행된다.** `ConflictCode` 15개 중 제약 계열 10개가
   `IntegrityViolationCode`에 동일한 이름으로 존재하고, `validate_plan_integrity`가 컴파일된 계획을
   대상으로 재검사한다. 나머지 4개는 fan-in 실패로 처리되고, 1개
   (`STRUCTURED_PROPOSALS_INCOMPATIBLE`)는 계획 제안자가 하나가 되면 성립하지 않는다.
2. **review는 안전 veto를 강제하던 지점이 아니다.** review는 Coordinator보다 **앞**에서 proposal을
   검사하므로 Coordinator의 출력을 막을 수 없다. "Coordinator 출력이 Safety veto를 덮을 수 없다"는
   불변조건을 실제로 지키는 것은 `coordinator_initial → compile → validate` 경로의 integrity
   validator다.
3. **의견 불일치 판정이 사실상 항상 발생한다.** `STRUCTURED_PROPOSALS_INCOMPATIBLE`이
   `exercise_prescriptions` 튜플의 완전 일치를 요구한다. 세 Agent가 독립적으로 동일한 처방에
   수렴하는 일은 실측에서 발생하지 않았다.
4. **review는 구현된 적이 없다.** `LangChainSpecialistAdapter`에 `areview`가 없고,
   `nodes.py`의 `except Exception`이 `AttributeError`를 삼켜 `V3_{role}_REVIEW_FAILED`라는
   도메인 실패 코드로 보고해 왔다. 충돌이 감지된 모든 실행이 fallback으로 갔다.
5. **ADR-0012의 V2 심의 저장소는 쓰이지 않는다.** `DeliberationRepository`는 테스트에서만
   호출되며 `decision_deliberations`와 `agent_review_events`에 쓰는 production 경로가 없다.

## 결정

### 1. V3 실행 순서

ADR-0013 1절의 6·7단계를 제거하고 다음 순서를 채택한다.

1. 결정적 `SafetyPolicyEngine`이 먼저 실행된다.
2. 결정적 constraint builder가 `ConstraintEnvelope`를 고정한다.
3. application loader가 ADR-0014 순서로 `ExercisePoolSnapshot`을 만든다.
4. Training·Recovery·Feasibility 세 LLM Agent가 동일한 envelope와 pool을 받아 병렬로 응답한다.
5. LLM Coordinator가 세 응답을 종합해 하나의 구조화 `PlanSpec`을 반환한다.
6. 결정적 Plan Compiler가 `PlanSpec`을 실행 블록으로 만든다.
7. 최종 integrity validator가 저장된 envelope 준수를 검사한다.
8. repairable violation은 Coordinator에 한 번만 돌려보낸다. 재실패 또는 non-repairable violation은
   결정적 fallback 또는 계획 없는 상태로 종료한다.

### 2. Agent 산출물의 역할 분리

| Agent | 산출물 | 성격 |
|---|---|---|
| Training | 승인 pool 안의 운동 계획 초안 (`exercise_prescriptions`) | 계획의 단일 소유자 |
| Recovery | 회복 관점의 조정 코드 (`adjustment_codes`) | Coordinator에 대한 권고 |
| Feasibility | 시간·장소·장비 관점의 조정 코드 (`adjustment_codes`) | Coordinator에 대한 권고 |

Training만 계획을 만든다. 이는 새 규칙이 아니라 기존 도메인 계약의 명시화다.
`SpecialistAgentProposal`은 이미 Training에 대해서만 `exercise_prescriptions`를 필수로 요구하고,
나머지 둘은 계획 또는 조정 코드 중 하나면 `READY`가 된다.

계획 제안자가 하나이므로 제안 간 불일치라는 상태 자체가 성립하지 않는다.

### 3. `adjustment_codes`의 지위

Recovery와 Feasibility의 `adjustment_codes`는 **권고이며 결정론적 강제 대상이 아니다.**
Coordinator payload로 전달되지만 Coordinator가 반영하지 않아도 서버가 거부하지 않는다.

이 지위를 명시하는 이유는 다음과 같다.

- 안전은 `ConstraintEnvelope`의 `excluded_exercise_ids`·`recovery_ceiling`과 integrity validator가
  완결적으로 강제한다. Recovery **Agent**가 여기에 더할 수 있는 안전은 없다.
- 두 Agent의 실제 역할은 승인된 안전 공간 **안에서** 더 나은 선택을 하도록 Coordinator에게
  관점을 제공하는 것이다.
- 강제력이 없는 것에 강제 장치를 붙이면 "Recovery Agent가 있으므로 안전하다"는 오해를 만든다.
  안전 논거는 Agent가 아니라 SafetyPolicyEngine과 validator에 둔다.

### 4. 유일한 결정론적 관문

Coordinator 출력에 대한 결정론적 검사는 integrity validator 하나다. 상류에 중복 관문을 두지 않는다.

`IntegrityViolationCode`는 envelope hash, pool hash, 요청 시간, 처방 스키마, 필수 운동,
pool 이탈, 안전 제외 운동, 장소, 장비, recovery ceiling, catalog 레코드 일치를 검사한다.

### 5. 재현성

`graph_version`을 새 값으로 올린다. 저장된 결정은 어느 그래프 구조가 만든 것인지 식별할 수 있어야
한다. `V3DecisionPersistenceBundle`에서 `conflict_result`와 `review_results`를 제거하되, 기존 저장
레코드는 파괴적으로 변경하지 않는다.

ADR-0012의 `decision_deliberations`, `agent_review_events`, `agent_proposal_revisions` 테이블은
쓰기를 중단하되 이번 릴리스에서 삭제하지 않는다(AGENTS.md 10절).

## 결정 이유

- Coordinator의 역할을 하나로 만든다. 제안 종합은 Coordinator의 임무이며, 그 앞에서 같은 일을
  부분적으로 시도하는 단계는 책임을 나눌 뿐 안전을 더하지 않는다.
- 결정론적 안전 강제력을 잃지 않는다. 제약 검사가 하류에서 전부 재실행되며, 검사 지점이
  proposal(상류)에서 컴파일된 계획(하류)으로 옮겨가는 것은 오히려 강화다. 사용자에게 나가는
  산출물을 검사하기 때문이다.
- 구현되지 않은 채 실패 코드만 남기던 경로를 제거한다.
- LLM 호출이 최대 8회(제안 3 + review 3 + coordinator + repair)에서 최대 5회로 줄어 지연과
  비용이 감소한다. 현재 reasoning 모델에서 지연이 실측 문제였다.
- 계획 소유자를 하나로 두어 세 Agent가 각자 계획을 만드는 토큰 낭비를 없앤다.

## 검토한 대안

1. 현재 구조 유지 + `areview` 구현
2. 현재 구조 유지 + 충돌 판정 기준 완화(운동 ID 집합 비교)
3. `adjustment_codes`를 결정론적 충돌 판정에 포함
4. Coordinator를 결정론적 규칙으로 대체하고 Agent를 제안자로만 사용

## 선택하지 않은 대안과 이유

1. **`areview` 구현** — 구현해도 Coordinator와의 역할 중복이 남는다. 어떤 Agent를 우선할지에 대한
   가중치를 새로 정의해야 하는데, 그 근거가 기존 계약에 없다.
2. **판정 기준 완화** — 세 Agent가 각자 계획을 만드는 구조가 그대로 남아 토큰과 지연이 유지된다.
   기준을 느슨하게 할수록 무엇을 검사하는지가 모호해진다.
3. **`adjustment_codes` 강제** — 조정 코드별 판정 규칙을 새로 정의해야 하고, 안전이 이미
   결정론적으로 강제되는 영역에 두 번째 강제 계층을 만든다. 3절의 이유로 채택하지 않는다.
4. **Coordinator 결정론화** — ADR-0013이 LLM 기반 루틴 합성을 채택한 취지를 되돌린다.

## 결과와 영향

- ADR-0013의 Safety-first 순서, Agent/Coordinator의 DB 접근 금지, LLM이 안전을 만들 수 없다는
  경계는 그대로 유지된다.
- ADR-0012는 `SUPERSEDED`가 된다. 2라운드 상호검토는 V2에서도 production 경로가 없었고 V3에서
  제거되므로 어느 경로의 목표 계약도 아니다.
- AGENTS.md 11절 골든 시나리오 6번의 문구를 실제 강제 지점(최종 검증)에 맞게 고친다.
- 그래프 노드 7개(`detect_conflicts`, `optional_reviews`, `review_*` 3개, `finalize_reviews`)와
  라우팅 2개(`after_conflicts`, `after_reviews`)가 제거된다.
- `backend/app/domain/agents/v3_conflicts.py`가 제거 대상이 된다.
- 공개 API 응답 필드는 변경하지 않는다.

## 보안·개인정보·호환성 영향

- 개인정보 경계는 변경되지 않는다. Agent payload 투영 규칙과 금지 필드 목록은 그대로다.
- LLM 호출 횟수가 줄어 외부 provider로 나가는 데이터 노출 지점이 줄어든다.
- Safety veto, 생성 금지, 요청 시간, pool, version 제약은 모두 유지된다.
- 저장된 기존 decision record는 변경하지 않는다. 새 `graph_version`으로 구분한다.
- V3는 DEMO 프로파일이며 production 승인 전이므로 운영 영향이 없다.

## 아직 확정되지 않은 사항

- 새 `graph_version` 문자열
- `decision_deliberations`·`agent_review_events`·`agent_proposal_revisions` 테이블의 실제 제거 시점
- Coordinator 프롬프트에서 세 응답의 우선순위를 어떻게 서술할지. 결정론적 서열은 두지 않으므로
  프롬프트 수준의 안내 문구만 남는다.
- V3 계획의 준비운동·마무리 구간 도입 여부(이슈 #174, 본 ADR과 독립)

## 후속 작업

1. 도메인 계약에서 Recovery·Feasibility의 `exercise_prescriptions` 제출을 거부하도록 강제한다.
   프롬프트 의존으로 두지 않는다.
2. 역할 분리에 맞춰 role prompt를 다시 쓰고 버전을 올린다.
3. 그래프에서 충돌·review 노드와 라우팅을 제거하고 `graph_version`을 올린다.
4. `v3_conflicts.py`와 관련 테스트를 제거한다.
5. 골든 시나리오와 안전 불변식 테스트를 갱신한다.
6. 다음 릴리스에서 V2 심의 테이블 제거를 별도 마이그레이션으로 처리한다.
