# TRACEABILITY.md

## 1. 목적

기획서의 기능 ID를 계약, 인수 조건, 테스트 케이스까지 추적한다. 요구사항 ID는 삭제 후 재사용하지 않는다.

## 2. ID 규칙

- 기능: 원문 `F###`
- 정책: 원문 `POL-###`
- 비기능: 원문 `NFR-###`
- 계약: `C-<영역>-###`
- 인수 조건: `AC-<요구사항>-##`
- 테스트: `TC-<요구사항>-##`

새 제품 요구사항 ID는 PM만 발급한다. 개발자가 빈 번호를 추정해 만들지 않는다.

## 3. 전체 추적 매트릭스

기준 NDJSON에는 47개 상위 그룹과 447개 세부 요구사항이 있다. 아래 표는 상위 그룹별 요약이며, 실제 구현·검수의 기준 ID는 `F###-#-#`, `POL-###-#-#`, `NFR-###-#-#` 형태의 세부 ID다. WBS·AC·TC ID는 WBS 추적표와 동일하게 유지하고, 상태가 `초안`, `탐색`, `정책안`, `가설`, `잠정`인 항목은 구현 완료로 간주하지 않는다.

POL-009~013은 2026-08-11 사용자 명시 승인과 `ACCEPTED` ADR-0004로 제품 문서 기준 승인이 완료되었다. 다만 사용자 요청에 따라 `docs/requirements/**` 원본의 `정책안`·`가설` 표기는 수정하지 않았으므로 아래 상태에 원본 미동기화를 명시한다.

| 요구사항 | WBS 연결 | 계약·문서 | 인수조건 | 테스트 | 상태 |
|---|---|---|---|---|---|
| F001 | 1.2, 1.3, 4.1, 5.1 | MVP_SCOPE·PROJECT_BRIEF | AC-F001-01 | TC-F001-01 | 초안 |
| F002 | 2.4, 2.7, 3.2, 3.3, 3.5, 4.5, 4.7, 5.2, 5.3 | MVP_SCOPE·DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-F002-01 | TC-F002-01 | 초안 |
| F003 | 2.1, 2.2, 2.3, 2.8, 4.10, 4.11, 5.2 | MVP_SCOPE·API_CONTRACT·DATA_MODEL | AC-F003-01 | TC-F003-01 | 탐색 |
| F004 | 2.4, 2.7, 2.8, 3.3, 4.8, 4.10, 4.11, 5.2 | MVP_SCOPE·API_CONTRACT·DATA_MODEL | AC-F004-01 | TC-F004-01 | 초안 |
| F005 | 2.4, 3.5, 4.9, 4.11, 5.2 | MVP_SCOPE·DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-F005-01 | TC-F005-01 | 초안 |
| F006 | 2.4, 보완-01, 4.7, 4.11, 5.2, 5.3 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-F006-01 | TC-F006-01 | 확정 |
| F007 | 2.4, 2.5, 보완-01, 4.7, 4.8, 4.9, 4.11, 5.2 | API_CONTRACT·DATA_MODEL | AC-F007-01 | TC-F007-01 | 초안 |
| F008 | 2.4, 2.8, 보완-02, 4.9, 5.2 | MVP_SCOPE·DATA_MODEL | AC-F008-01 | TC-F008-01 | 초안 |
| F009 | 3.5, 4.9, 5.2 | MVP_SCOPE·API_CONTRACT·DATA_MODEL | AC-F009-01 | TC-F009-01 | 초안 |
| F010 | 4.4, 4.11, 5.2, 5.4 | MVP_SCOPE·API_CONTRACT | AC-F010-01 | TC-F010-01 | 초안 |
| F011 | 4.1, 4.10, 4.11, 5.2 | MVP_SCOPE·API_CONTRACT·DATA_MODEL | AC-F011-01 | TC-F011-01 | 초안 |
| F025 | 2.1, 2.4, 4.1, 4.4, 4.11, 5.2, 5.4 | MVP_SCOPE·API_CONTRACT·DATA_MODEL | AC-F025-01 | TC-F025-01 | 초안 |
| F026 | 3.2, 3.3, 3.5, 4.5, 4.11, 5.2 | MVP_SCOPE·DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-F026-01 | TC-F026-01 | 초안 |
| F027 | 3.5, 4.5, 4.7, 4.11, 5.2 | MVP_SCOPE·API_CONTRACT·DATA_MODEL | AC-F027-01 | TC-F027-01 | 초안 |
| F028 | 보완-01, 4.7, 4.11, 5.2, 5.3 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-F028-01 | TC-F028-01 | 확정 |
| F029 | 3.5, 4.6, 5.2 | MVP_SCOPE·API_CONTRACT·DATA_MODEL | AC-F029-01 | TC-F029-01 | 초안 |
| POL-001 | 3.5, 4.9, 5.2 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL001-01 | TC-POL001-01 | 확정 |
| POL-002 | 4.9, 4.11, 5.2 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL002-01 | TC-POL002-01 | 확정 |
| POL-003 | 3.5, 4.9, 4.11, 5.2 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL003-01 | TC-POL003-01 | 확정 |
| POL-004 | 보완-01, 4.7, 5.2, 5.3 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL004-01 | TC-POL004-01 | 확정 |
| POL-005 | 보완-01, 2.8, 4.7, 4.10, 5.2, 5.3 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL005-01 | TC-POL005-01 | 확정 |
| POL-006 | 4.8, 4.9, 5.2 | API_CONTRACT·DATA_MODEL·TEST_STRATEGY | AC-POL006-01 | TC-POL006-01 | 초안 |
| POL-007 | 3.2, 3.3, 3.4, 3.5, 4.5, 4.7, 5.2, 5.3 | DOMAIN_RULES·API_CONTRACT | AC-POL007-01 | TC-POL007-01 | 확정 |
| POL-008 | 2.7, 3.2, 3.4, 3.7, 3.8, 5.3 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL008-01 | TC-POL008-01 | 확정 |
| POL-009 | 2.1, 2.5, 4.4, 4.10, 4.11, 5.4 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL009-01 | TC-POL009-01 | 승인·원본 미동기화 |
| POL-010 | 2.1, 2.3, 2.4, 2.5, 2.8, 5.4 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL010-01 | TC-POL010-01 | 승인·원본 미동기화 |
| POL-011 | 2.4, 2.5, 4.4, 4.11, 5.4 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL011-01 | TC-POL011-01 | 승인·원본 미동기화 |
| POL-012 | 보완-03, 4.4, 5.4 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL012-01 | TC-POL012-01 | 승인·원본 미동기화 |
| POL-013 | 1.3, 보완-04 | MVP_SCOPE·API_CONTRACT | AC-POL013-01 | TC-POL013-01 | 승인·원본 미동기화 |
| NFR-001 | 3.5, 4.6, 4.9, 5.2 | MVP_SCOPE·API_CONTRACT·DATA_MODEL | AC-NFR001-01 | TC-NFR001-01 | 필수 |
| NFR-002 | 1.2, 5.1, 5.7 | TRACEABILITY | AC-NFR002-01 | TC-NFR002-01 | 필수 |
| NFR-003 | 3.4, 3.5, 3.8, 5.3 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-NFR003-01 | TC-NFR003-01 | 필수 |
| NFR-004 | 2.1, 2.5, 3.5, 4.4, 5.4 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-NFR004-01 | TC-NFR004-01 | 필수 |
| NFR-005 | 2.5, 4.4, 4.10, 4.11, 5.4 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-NFR005-01 | TC-NFR005-01 | 필수 |
| NFR-006 | 1.2, 3.7, 5.1, 5.2, 5.3, 5.7 | TRACEABILITY·TEST_STRATEGY | AC-NFR006-01 | TC-NFR006-01 | 필수 |

F012~F023은 요구사항 정의서상 MVP 이후 확장 기능이다. 각 ID는 삭제·재사용하지 않고, 별도 확장 WBS·AC·TC를 만들기 전까지 `POST_MVP/PLANNED`로 관리한다.

| 확장 ID | 범위 | WBS | 인수조건 | 테스트 | 상태 |
|---|---|---|---|---|---|
| F012 | 기능 제안 | 별도 확장 WBS 예정 | AC-F012-01 | TC-F012-01 | POST_MVP/PLANNED |
| F013 | 영상 추천 | 별도 확장 WBS 예정 | AC-F013-01 | TC-F013-01 | POST_MVP/PLANNED |
| F014 | 웰니스 코인 | 별도 확장 WBS 예정 | AC-F014-01 | TC-F014-01 | POST_MVP/PLANNED |
| F015 | 혜택 교환 | 별도 확장 WBS 예정 | AC-F015-01 | TC-F015-01 | POST_MVP/PLANNED |
| F016 | 운동용품 추천 | 별도 확장 WBS 예정 | AC-F016-01 | TC-F016-01 | POST_MVP/PLANNED |
| F017 | 쇼핑 연결 | 별도 확장 WBS 예정 | AC-F017-01 | TC-F017-01 | POST_MVP/PLANNED |
| F018 | 브랜드 캠페인 | 별도 확장 WBS 예정 | AC-F018-01 | TC-F018-01 | POST_MVP/PLANNED |
| F019 | AI 상담 | 별도 확장 WBS 예정 | AC-F019-01 | TC-F019-01 | POST_MVP/PLANNED |
| F020 | 에이전트 능력 활성화 | 별도 확장 WBS 예정 | AC-F020-01 | TC-F020-01 | POST_MVP/PLANNED |
| F021 | 회복 에이전트 | 별도 확장 WBS 예정 | AC-F021-01 | TC-F021-01 | POST_MVP/PLANNED |
| F022 | 집중 에이전트 | 별도 확장 WBS 예정 | AC-F022-01 | TC-F022-01 | POST_MVP/PLANNED |
| F023 | 영양 에이전트 | 별도 확장 WBS 예정 | AC-F023-01 | TC-F023-01 | POST_MVP/PLANNED |

### 3.1 세부 요구사항 추적 규칙

- 상위 그룹 행의 상태는 하위 세부 항목 중 가장 낮은 상태를 따른다. 상위 행만 `완료`로 표시하지 않는다.
- 세부 요구사항마다 WBS, 계약 문서 또는 API·데이터 필드, 인수조건, 테스트 케이스, owner를 연결한다.
- 요구사항 정의서의 ID와 문구는 임의로 합치거나 재사용하지 않는다. 범위가 바뀌면 새 세부 ID 또는 변경 기록을 추가한다.
- F002의 멀티 에이전트 구조는 `TrainingAgent`, `RecoveryAgent`, `SafetyAgent`의 3개 proposal과 `Coordinator`(의장)의 최종 통합으로 추적한다. `F002-1-34`, `F002-1-35`, `F002-1-38`, `F002-1-48~60`은 이 계약과 연결한다.
- F029의 회의 UI는 `TrainingAgent`, `RecoveryAgent`, `SafetyAgent`, `Coordinator`, `FinalSafetyGate` 요약을 표시하되, `F029-1-13`에 따라 원래 루틴 선택 UI는 제공하지 않는다.
- `F002-1-51`, `F002-1-52`, `F002-1-56`에 따라 lighter·original은 공개 선택지로 추적하지 않고 내부 후보·안전 검증 기록으로만 관리한다.
- `F002-1-55` 제목의 `primary`는 요구사항 원문의 legacy 명칭이며 공개 계약의 `FINAL_ROUTINE`에 매핑한다. 요구사항 원문 제목 변경은 PM만 수행한다.

## 4. PR 적용

각 기능 PR은 관련 행을 갱신하고 실제 테스트 파일이 생기면 테스트 ID 옆에 경로를 연결한다. 계약 변경만 있고 테스트가 아직 없는 경우 상태를 `PLANNED`로 명시하며 완료로 간주하지 않는다.

## 5. 대안과 선택 이유

스프레드시트 하나만 진실 공급원으로 사용하지 않는다. 원문 요구사항 ID는 보존하되 구현 계약과 테스트 링크는 저장소에서 함께 버전 관리한다.

## 6. 아직 확정되지 않은 사항과 질문

- 전체 47개 요구사항의 owner와 WBS 연결 상태
- 멀티 에이전트 로직 설계 후 Training·Recovery·Safety proposal, Coordinator, FinalSafetyGate, 회의 UI 계약과 관련 AC·TC 확정
- F003 웨어러블의 지원 기기·제공자와 원본·요약 필드의 품질·라이선스 기준
- F004 체중 기반 예상 소모 칼로리 산식·단위·반올림 기준
- F011 캘린더 제공자·조회 범위·시간대·빈 시간 계산 규칙
- 추적성 검사를 CI에서 자동화할 시점
