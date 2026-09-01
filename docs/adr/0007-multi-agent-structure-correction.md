# ADR-0007: 멀티 에이전트 구조 정정

- 상태: ACCEPTED
- 날짜: 2026-08-12
- 소유자: 제품·개발 공동
- 승인자: PM + 개발팀장
- 관계: ADR-0002 대체
- 후속 결정: ADR-0013(`ACCEPTED`, V3 목표). V3 구현·검증과 production 전환 승인 전에는 본 ADR이
  production 기준
- 관련 요구사항/이슈: `F002`, `F029`, `POL-008`, `NFR-003`

## 배경

ADR-0002는 Training·Recovery·Safety 세 proposal과 Coordinator, 독립 FinalSafetyGate 구조를 결정했다. 그러나 현재 요구사항·아키텍처·도메인 규칙·API·데이터 모델은 Feasibility proposal을 포함한 4개 proposal과 Coordinator 구조를 기준으로 작성되어 있다. 문서 간 에이전트 수와 안전 결정 경계가 달라 구현 기준이 일치하지 않는다.

## 결정

- Training·Recovery·Safety·Feasibility 4개 proposal과 Coordinator 구조를 사용한다.
- 4개 proposal은 공통 입력과 검수된 기본 후보를 바탕으로 병렬 실행한다.
- Coordinator는 4개 proposal을 종합해 최종 운동 계획 하나를 결정한다.
- 독립 FinalSafetyGate는 두지 않는다.
- SafetyAgent의 결정적 안전 규칙과 veto 의견은 Coordinator가 우선 반영한다.
- 필수 proposal 누락 또는 `FAILED`, 필수 규칙 실패, 저장 실패가 발생하면 운동 계획을 성공 응답하지 않고 `FAILED`로 처리한다.
- 안전 상태와 실패 안전 규칙은 결정적 규칙으로 유지하며 Coordinator나 LLM이 안전 veto를 해제할 수 없다.

## 결정 이유

현재 요구사항과 최신 설계 문서가 공통으로 정의한 4개 proposal과 Coordinator의 책임 경계를 일치시키고, 별도 FinalSafetyGate를 추가해 동일한 안전 판단을 중복 실행하거나 서로 다른 결과를 만드는 위험을 줄이기 위해서다.

## 검토한 대안

- Training·Recovery·Safety 3개 proposal과 Coordinator 뒤에 독립 FinalSafetyGate를 두는 구조
- Feasibility를 Coordinator 내부 로직으로만 처리하는 구조
- 모든 proposal을 순차 실행하는 구조

## 선택하지 않은 대안과 이유

- 독립 FinalSafetyGate 구조는 현재 요구사항·아키텍처·도메인 규칙의 4개 proposal 구조와 충돌한다.
- Feasibility를 Coordinator 내부에 숨기면 실행 가능성 판단의 책임과 기록을 proposal 단위로 추적할 수 없다.
- 순차 실행은 proposal 간 독립성을 활용하지 못하고 결정 지연을 증가시킨다.

## 결과와 영향

- ADR-0002의 상위 에이전트 구조 결정은 본 ADR로 대체한다.
- Architecture·Domain Rules·API Contract·Data Model·Technical Plan·MVP Scope·Test Strategy·Traceability는 4개 proposal과 Coordinator 구조를 기준으로 유지·동기화한다.
- 공개 회의 요약의 표시 순서는 Training → Recovery → Safety → Feasibility → Coordinator로 유지한다.
- 독립 FinalSafetyGate 전용 실행·저장·응답 필드는 추가하지 않는다.
- 본 ADR이 승인되면 ADR-0002의 상태를 `SUPERSEDED`로 갱신한다.

## 보안·개인정보·호환성 영향

SafetyAgent의 결정적 안전 veto는 Coordinator가 우회할 수 없다. 내부 프롬프트와 숨은 추론은 저장하거나 공개하지 않으며, proposal과 최종 결정은 별도로 저장해 결정 재현성을 유지한다. 기존 공개 API의 안전 상태·실패 응답 계약을 깨뜨리지 않도록 관련 문서와 호환성 테스트를 함께 갱신한다.

## 아직 확정되지 않은 사항

- 4개 proposal의 상세 입력·출력 JSON 구조
- proposal·Coordinator의 graph, policy, prompt 버전 필드
- proposal 재시도와 timeout 정책
- 공개 요약의 세부 필드와 문구

## 후속 작업

1. 승인된 4개 proposal·Coordinator 구조와 관련 문서의 동기화 상태를 유지·검토한다.
2. ADR-0002는 본 ADR로 대체된 `SUPERSEDED` 상태를 유지한다.
3. 관련 API·데이터·테스트 문서와 추적성 ID를 검토·동기화한다.
4. 4개 proposal 병렬 실행, Coordinator 통합, Safety veto 불변, 실패 안전 동작의 golden scenario와 회귀 테스트를 추가한다.
