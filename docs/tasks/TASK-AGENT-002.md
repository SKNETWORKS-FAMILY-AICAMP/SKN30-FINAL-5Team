# TASK-AGENT-002: 2라운드 구조화 상호검토 계약 동결

- Primary owner: 백엔드 개발팀장
- Reviewers: 백엔드 담당자, PM, 외부 도메인 검수자
- 관련 요구사항: `F002`, `F029`, `POL-008`, `NFR-003`, `NFR-006`
- 관련 ADR: `ADR-0007`, `ADR-0011`, `ADR-0012`(`ACCEPTED`)
- 목표 브랜치: `codex/agent-deliberation-v2-adr`
- 현재 상태: `COMPLETE` (2026-08-20)

## 배경과 사용자 가치

현재 구현은 동일한 입력과 승인 후보를 받은 Training·Recovery·Safety·Feasibility Agent가
각각 한 번 구조화 proposal을 제출하고 결정적 Coordinator가 이를 취합한다. 역할별 의견과
안전 veto는 재현 가능하게 저장되지만, Agent가 다른 Agent의 제약을 확인하고 선호를 조정하는
상호검토 단계는 없다.

사용자가 서로 다른 전문성이 최종 루틴에 어떻게 반영됐는지 이해할 수 있도록 하면서도 자유
형식 토론, LLM 안전 판단, 무제한 반복을 도입하지 않는 2라운드 구조화 상호검토 계약이 필요하다.

## 포함 범위

- 기존 네 Agent와 Coordinator 책임을 유지하는 2라운드 목표 구조
- Round 1 독립 proposal, 결정적 conflict detector, 조건부 Round 2 review의 상태 전이
- Agent별 hard constraint와 조정 가능한 preference 권한
- `AgentReview`와 revised proposal의 내부 `0.x` 논리 계약
- Safety veto·제외·상태의 단조성 및 요청 시간·승인 후보 불변식
- Round 1·Round 2 누락, 실패, 추가 입력 필요와 미해결 충돌의 fail-closed 계약
- 재현에 필요한 proposal hash, conflict, review, graph·policy·precedence version
- 공개 deliberation narration의 code-only 입력과 템플릿/LLM 경계
- 프레임워크 독립 기준 구현 후 LangGraph를 재평가하는 도입 게이트
- 후속 DB·API·테스트 작업에 전달할 논리 계약

## 제외 범위

- `backend/app/**` 런타임 구현 변경
- SQLAlchemy model, repository, Alembic migration
- 공개 `DecisionResponse` 필드 추가·삭제·이름 변경
- LangGraph production dependency와 checkpointer 도입
- LLM을 Agent 판단, conflict 탐지, 후보 생성·선택에 사용
- 자유 형식 Agent 토론, chain-of-thought 저장·공개
- 새로운 안전 임계값, 통증 분류, 복귀 상한 또는 운동 데이터 승인
- 독립적인 FinalSafetyGate 재도입

## 인수 조건

1. 활성 V1과 승인된 V2 목표가 문서에서 명확히 구분되며, ADR 승인을 구현 완료로 표현하지 않는다.
2. V2는 Round 1의 네 필수 proposal을 동일한 immutable 입력과 승인 후보로 실행한다.
3. Round 1에 `FAILED`·누락이 있으면 `FAILED`, `NEEDS_INPUT`이 있으면 `NEEDS_INPUT`으로 종료하고
   Round 2나 성공 계획으로 진행하지 않는다.
4. conflict detector는 proposal·후보·승인 정책만 사용해 canonical conflict code를 결정적으로 만든다.
5. 충돌이 있을 때만 영향받는 Agent를 Round 2 review 대상으로 지정하고, 비대상 Agent는
   `NOT_REQUIRED` event로 기록한다. 충돌이 없으면 네 Agent 모두 Agent 호출 없는 `NOT_REQUIRED`다.
6. 대상 review 누락·`FAILED`는 decision run `FAILED`, `NEEDS_INPUT`은 계획 없는
   `NEEDS_INPUT`으로 처리한다.
7. Safety veto와 제외는 제거할 수 없고 `false -> true` 또는 추가 제외 방향으로만 강화할 수 있다.
8. 요청 시간, 승인 후보 집합, 입력·정책·카탈로그·규칙 버전은 Round 2에서 변경할 수 없다.
9. Safety·Feasibility·Recovery의 hard constraint와 Training 목표를 동시에 만족하는 후보가 없으면
   목표·시간·안전을 임의 완화하지 않고 기존 계약의 `REST`, `NEEDS_INPUT` 또는 `FAILED`로 종료한다.
10. LLM은 최종 결정 이후 공개 가능한 machine code를 한 번에 문장으로 변환할 수 있을 뿐,
    proposal·review·conflict·action·후보·안전 상태를 만들거나 변경하지 않는다.
11. Round 1, conflict, Round 2, Coordinator 결과의 해시·버전 저장 요구와 삭제·보존 경계가 정의된다.
12. LangGraph는 기준 구현의 재현성·안전·지연 비교 후 별도 승인하는 선택지로 남는다.

## 변경 예상 파일

- `docs/tasks/TASK-AGENT-002.md`
- `docs/adr/0012-structured-agent-deliberation.md`
- `docs/ARCHITECTURE.md`
- `docs/DOMAIN_RULES.md`
- `docs/DATA_MODEL.md`
- `docs/TECHNICAL_PLAN.md`
- `docs/TEST_STRATEGY.md`
- `docs/TRACEABILITY.md`

## API 영향

A1에서는 공개 API 변경이 없다. 기존 `public_agent_summaries`를 유지한다. Round 2 공개 event는
프론트엔드·백엔드·개발팀장 공동 검토가 있는 별도 additive API task에서 optional 필드로 제안한다.

## DB·마이그레이션 영향

A1에서는 migration이 없다. 후속 persistence task는 기존 `agent_proposals`와 final decision을
깨지 않고 `decision_deliberations`와 `agent_review_events`를 additive하게 저장하는 방안을 검토한다.

## 안전·개인정보·보안 영향

- Safety veto와 제외 운동은 review나 Coordinator가 완화할 수 없다.
- 직접 식별자, 생년월일·만 나이, 자유 형식 체크인, 원시 건강·웨어러블 값은 review·LLM 입력에서 제외한다.
- application log, exception text, prompt 원문과 hidden reasoning은 proposal·review·공개 응답에 넣지 않는다.
- 통증·이상 반응·veto가 있는 결정은 검수 템플릿을 사용하고 LLM narration을 호출하지 않는다.

## 선행 관계와 차단 요소

- ADR-0007의 네 Agent, 결정적 Coordinator, 독립 FinalSafetyGate 없음 계약을 유지한다.
- ADR-0011의 narration-only LLM 경계를 유지한다.
- ADR-0012는 필수 reviewer에게 `ACCEPTED`되었으며, A2 런타임 구현은 A1 병합 후 별도 브랜치와
  task에서 시작한다.
- 새로운 안전 수치가 필요하면 본 task에서 정하지 않고 별도 안전 정책 task로 분리한다.

## 테스트 계획

A1은 문서 작업이므로 링크·상태·용어 정합성을 검사한다. 후속 구현의 필수 테스트 계약은 다음과 같다.

- no-conflict에서 Round 2 비실행과 V1 동등 결과
- conflict·review 대상의 canonical ordering
- Safety veto·제외 단조성 속성 테스트
- review 누락·실패·invalid result fail-closed
- 요청 시간·승인 후보·버전 불변
- 동일 입력·버전의 conflict/review/final 결과 재현
- LLM 비활성·실패·거부 시 동일 결정과 전체 템플릿 폴백
- application log·직접 식별자·원시 건강 데이터의 review/LLM payload 미포함

## 수동 확인

1. `rg -n "ADR-0012|Structured Deliberation|구조화 상호검토" docs`
2. `rg -n "LangGraph" docs/ARCHITECTURE.md docs/TECHNICAL_PLAN.md docs/adr/0012-structured-agent-deliberation.md`
3. `git diff --check`
4. 변경된 계약에서 활성 V1과 승인된 V2 목표의 구현 상태가 혼동되지 않는지 검토한다.

## 알려진 제한과 후속 작업

- A2: 프레임워크 독립 `DeliberationState`, conflict detector, `AgentReview` 구현
- A3: V1/V2 golden·reproducibility·latency 비교
- B2: PostgreSQL additive persistence와 migration
- B3: optional 공개 deliberation event API와 프론트 호환성 검토
- A4: 기존 narration adapter의 code-only batch 확장
- A5: 기준 구현과 LangGraph PoC 비교 및 production 도입 여부 ADR
