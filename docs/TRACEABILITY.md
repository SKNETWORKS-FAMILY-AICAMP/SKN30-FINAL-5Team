# TRACEABILITY.md

## 1. 목적

기획서의 기능 ID를 계약, 인수 조건, 테스트 케이스까지 추적한다. 요구사항 ID는 삭제 후 재사용하지 않는다.

## 2. ID 규칙

- 기능: 원문 `F###`
- 정책: 원문 `POL-###`
- 비기능: 원문 `NFR-###`
- 계약: `C-<영역>-###`
- 상위 그룹 요약 인수 조건: `AC-<요구사항>-##`
- 상위 그룹 요약 테스트: `TC-<요구사항>-##`
- WBS 세부 인수 조건: `AC-<세부 요구사항 ID>`
- WBS 세부 테스트: `TC-<세부 요구사항 ID>`

새 제품 요구사항 ID는 PM만 발급한다. 개발자가 빈 번호를 추정해 만들지 않는다.

## 3. 전체 추적 매트릭스

기준 NDJSON에는 47개 상위 그룹과 447개 세부 요구사항이 있다. 아래 표는 상위 그룹별 요약이며, 실제 구현·검수의 기준 ID는 `F###-#-#`, `POL-###-#-#`, `NFR-###-#-#` 형태의 세부 ID다. WBS 상세 행이 존재하는 그룹은 WBS의 세부 AC/TC ID를 사용하고, 아래 상위 그룹 요약 행은 요약용 AC/TC ID를 사용한다.

구현 판정 기준은 2026-08-20 `develop`의 `bc55131`이다. 계약 승인과 구현 완료를 분리하며 다음
상태만 사용한다.

- `IMPLEMENTED`: 계약, 실행 코드, 저장 경계(해당 시), 테스트, 병합 PR 근거가 모두 존재
- `PARTIAL`: 일부 하위 AC 또는 운영/provider 경로가 남음
- `DEFERRED`: MVP 요구는 유지하지만 명시적 보류 또는 외부 선행조건으로 실행 경로가 없음
- `MVP_EXCLUDED`: 요구사항 정의서에서 MVP 이후 범위로 분리

`IMPLEMENTED`는 저장소 근거의 존재를 뜻하며 이번 문서 변경에서 전체 테스트 통과를 재선언하는
표현이 아니다. 상위 그룹은 하위 항목 중 가장 낮은 상태를 따른다.

| 구분 | `IMPLEMENTED` | `PARTIAL` | `DEFERRED` | `MVP_EXCLUDED` |
|---|---:|---:|---:|---:|
| MVP 기능 F001~F011, F025~F029 | 9 | 4 | 2 | 1 |
| 정책·비기능 POL-001~013, NFR-001~006 | 14 | 5 | 0 | 0 |
| 확장 기능 F012~F023 | 0 | 0 | 0 | 12 |

POL-009~013은 2026-08-11 사용자 명시 승인과 `ACCEPTED` ADR-0004에 따라 계약 기준으로 적용한다. POL-011의 삭제 상태·provider 실패·30일 restore tombstone 상세 계약은 `ACCEPTED` ADR-0008을 따른다. F011의 Google Calendar 계약은 `ACCEPTED` ADR-0010에 있지만, PR #96에서 실제 연동을 보류했으므로 구현 상태는 `DEFERRED`다. F010의 provider-neutral 경계는 ADR-0009에 있으나 실제 server-side Google·Kakao·Naver exchange adapter/API가 없어 `PARTIAL`이다. 멀티 에이전트 production 구조는 `ACCEPTED` ADR-0007을 기준으로 한다. ADR-0012와 TASK-AGENT-002는 2라운드 구조화 상호검토 V2의 승인된 목표 계약이지만 구현 전에는 F002·F029 완료 증거에 포함하지 않는다. ADR-0013과 TASK-AGENT-003은 Safety-first LangChain/LangGraph LLM 멀티에이전트 V3의 `ACCEPTED` 목표 계약이지만 구현·shadow 평가와 production 전환 전에는 기존 상태를 올리거나 완료 증거로 사용하지 않는다. Qdrant retrieval ADR-0014는 `ACCEPTED`다.

### 3.1 MVP 기능 구현 증거

| 요구사항 | 인수조건 | API·DB | 코드 | 테스트 | 병합 PR | 상태 |
|---|---|---|---|---|---|---|
| F001 | AC-F001-01 | API·DB 없음 | `frontend/src/features/home/HomeScreen.tsx`, `frontend/src/features/onboarding/OnboardingScreen.tsx`, `frontend/src/features/weekly/WeeklyReportScreen.tsx` | `frontend/tests/HomeScreen.test.tsx`, `frontend/tests/demoFlow.test.tsx`, `frontend/tests/WeeklyReportScreen.test.tsx` | #75·#81·#92·#95 | `IMPLEMENTED` |
| F002 | AC-F002-1-1~1-60 | `/decisions`; `decision_runs`, `agent_proposals`, `plan_candidates`, `safety_reviews`, `decision_options` | `backend/app/modules/decisions/**`, `backend/app/domain/agents/**`, `backend/app/domain/rules/{duration,safety,return_mode}.py` | `backend/tests/unit/test_decision_service.py`, `backend/tests/unit/test_decision_agents.py`, `backend/tests/scenarios/test_decision_service_golden.py`, persistence replay tests | #9·#13·#17·#19·#21·#22·#41·#70·#72·#77·#78·#79 | `PARTIAL` — 60개 하위 AC의 개별 자동 매핑과 외부 입력 연동이 남음 |
| F003 | AC-F003-01 | `/wearables/**`와 wearable table 없음 | 수동 체크인·블록 완료 폴백만 구현 | `test_workout_execution.py`, `test_decision_service_golden.py` | #20·#78·#96 | `DEFERRED` |
| F004 | AC-F004-01 | 없음 | 없음 | 없음 | — | `MVP_EXCLUDED` |
| F005 | AC-F005-01 | `/weeks/{week}/report`, `/weekly-reports/{id}`; `user_weeks`, `weekly_reports` | `backend/app/modules/weekly_reports/**`, `frontend/src/features/weekly/**` | weekly report unit·API·integration tests, `frontend/tests/WeeklyReportScreen.test.tsx` | #26·#27·#81·#92·#95 | `IMPLEMENTED` |
| F006 | AC-F006-01 | `/workout-sessions/**`; workout session/item tables | `backend/app/modules/workouts/**`, workout UI | workout unit·API·integration tests, `frontend/tests/WorkoutScreen.test.tsx` | #24·#25·#71·#81·#92 | `IMPLEMENTED` |
| F007 | AC-F007-01 | timer/additional-activity/safety-event endpoints와 event tables | workout service·repository·domain execution rules | `test_workout_execution.py`, `test_workouts.py`, `test_workout_repository.py` | #24·#25·#71 | `IMPLEMENTED` |
| F008 | AC-F008-01 | weekly report aggregate JSON fields | `WeeklyReportService`의 completion·blocker·weekday 집계 | weekly report unit·API tests | #26·#27 | `PARTIAL` — 고완료 시간대·운동유형·강도 값은 현재 빈 목록 |
| F009 | AC-F009-01 | weekly report `summary`, `decision_summary` | 결정적 요약과 report UI | weekly report unit·API·UI tests | #26·#27·#81·#92·#95 | `PARTIAL` — 리포트는 구현됐으나 별도 AI 회고 생성은 없음 |
| F010 | AC-F010-01 | `users`, `user_identities`; social exchange API 없음 | Firebase token 검증·내부 identity 연결 | auth provider·Firebase·identity tests | #12·#32·#93 | `PARTIAL` |
| F011 | AC-F011-1-1~1-8 | calendar tables는 있으나 `/calendar/**` 없음 | contract·domain rules·provider port·repository까지만 존재 | calendar unit·integration·golden tests | #33~#37·#96 | `DEFERRED` |
| F025 | AC-F025-01 | `/me/onboarding`, `/me/consents`; profile·consent tables | profile service·repository·onboarding UI | onboarding/profile API·integration·UI tests | #14·#15·#66·#68·#85·#89·#91·#93 | `IMPLEMENTED` |
| F026 | AC-F026-01 | `/routines`, `/weeks/{week}/plan`; routine·week tables | routine·weekly plan services | routine/weekly plan unit·API·integration tests | #18·#28·#41 | `IMPLEMENTED` |
| F027 | AC-F027-01 | `/weeks/{week}/plan-revisions`; `weekly_plan_revisions` | weekly plan service와 홈 수정 UI | weekly plan unit·API·integration, Home UI tests | #28·#75·#81·#92 | `IMPLEMENTED` |
| F028 | AC-F028-01 | workout session mutation endpoints와 outcome fields | workout execution rules·service·UI | workout unit·API·integration·golden·UI tests | #23·#24·#25·#81·#92 | `IMPLEMENTED` |
| F029 | AC-F029-1-1~1-15 | decision `public_agent_summaries`; proposal tables | 4-agent summary + Coordinator 결과 UI | agent/coordinator/decision tests, `HomeScreen.test.tsx` | #13·#17·#41·#75·#77·#78 | `IMPLEMENTED` |

### 3.2 정책·비기능 구현 증거

| 요구사항 | 주요 코드·저장 근거 | 테스트 근거 | 병합 PR | 상태 |
|---|---|---|---|---|
| POL-001~003 | `domain/rules/weekly_report.py`, weekly report/plan services와 tables | weekly policy·service·API·repository tests | #26~#28 | `IMPLEMENTED` |
| POL-004~006 | `domain/rules/workout_execution.py`, workout service와 outcome/feedback tables | workout execution·service·API·repository·golden tests | #24·#25 | `IMPLEMENTED` |
| POL-007 | `domain/rules/duration.py`, decision service | duration·decision golden tests | #9·#19·#78 | `IMPLEMENTED` |
| POL-008 | `domain/rules/safety.py`, approved safety rules·alternatives, decision/workout safety flows | safety unit·golden·decision/workout tests | #11·#23·#65·#69·#72·#78·#101 | `IMPLEMENTED` |
| POL-009~010 | consent/profile 저장과 수동 fallback은 구현; 실제 wearable/calendar provider 없음 | consent, external-context, fallback tests | #15·#33~#37·#96 | `PARTIAL` |
| POL-011 | account deletion job/audit, 즉시 접근 차단·retention service | unit·API·integration·golden tests | #29·#30 | `IMPLEMENTED` |
| POL-012 | `domain/rules/return_mode.py`, decision/workout 반영 | return mode unit·golden tests | #23·#78 | `IMPLEMENTED` |
| POL-013 | AI trial 기간 저장·응답은 구현; 구독 결제·권한 전이는 없음 | identity/profile tests | #12·#15 | `PARTIAL` |
| NFR-001 | 검수 템플릿·선택적 LLM 설명, `decision_explanations` | explanation·LLM fallback unit/golden tests | #79 | `IMPLEMENTED` |
| NFR-002 | 요구사항 ID와 수동 문서 추적 | 이번 task의 JSON·경로·diff 검사 | — | `PARTIAL` — CI 자동 추적 없음 |
| NFR-003 | fail-closed agent·safety·persistence 경계 | decision/safety/fallback golden tests | #11·#13·#17·#19·#21·#22·#78 | `IMPLEMENTED` |
| NFR-004 | 생년월일 암호화, 최소 snapshot, 계정 삭제 | birthdate·profile·deletion tests | #7·#14·#15·#29·#30 | `IMPLEMENTED` |
| NFR-005 | Firebase 검증·마스킹·owner-scoped reads 구현; 외부 provider secret lifecycle 미완성 | auth/config/ownership/deletion tests | #8·#12·#29·#30·#71·#93 | `PARTIAL` |
| NFR-006 | 72개 파일, test 함수 594개(현재 non-integration parametrized collection 821개) | `backend/tests/**` | #19·#21·#78 외 기능 PR | `IMPLEMENTED` |

### 3.3 계약·WBS 상태 요약

| 요구사항 | WBS 연결 | 계약·문서 | 인수조건 | 테스트 | 상태 |
|---|---|---|---|---|---|
| F001 | 1.2, 1.3, 4.1, 5.1 | MVP_SCOPE·PROJECT_BRIEF | AC-F001-01 | TC-F001-01 | `IMPLEMENTED` |
| F002 | 2.4, 2.7, 3.2, 3.3, 3.5, 4.5, 4.7, 5.2, 5.3 | MVP_SCOPE·PROJECT_BRIEF·ARCHITECTURE·DOMAIN_RULES·API_CONTRACT·DATA_MODEL·TECHNICAL_PLAN·IMPLEMENTATION_PLAN·TEST_STRATEGY·ADR-0007·ADR-0012·ADR-0013(ACCEPTED 목표)·ADR-0014(ACCEPTED 목표) | AC-F002-1-1~1-60 | TC-F002-1-1~1-60 | `PARTIAL` |
| F003 | 2.1, 2.2, 2.3, 2.8, 4.10, 4.11, 5.2 | MVP_SCOPE·API_CONTRACT·DATA_MODEL·ADR-0006 | AC-F003-01 | TC-F003-01 | `DEFERRED` |
| F004 | 2.4, 2.7, 2.8, 3.3, 4.8, 4.10, 4.11, 5.2 | MVP_SCOPE·API_CONTRACT·DATA_MODEL·ADR-0006 | AC-F004-01 | TC-F004-01 | `MVP_EXCLUDED` |
| F005 | 2.4, 3.5, 4.9, 4.11, 5.2 | MVP_SCOPE·DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-F005-01 | TC-F005-01 | `IMPLEMENTED` |
| F006 | 2.4, 보완-01, 4.7, 4.11, 5.2, 5.3 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-F006-01 | TC-F006-01 | `IMPLEMENTED` |
| F007 | 2.4, 2.5, 보완-01, 4.7, 4.8, 4.9, 4.11, 5.2 | API_CONTRACT·DATA_MODEL | AC-F007-01 | TC-F007-01 | `IMPLEMENTED` |
| F008 | 2.4, 2.8, 보완-02, 4.9, 5.2 | MVP_SCOPE·DATA_MODEL | AC-F008-01 | TC-F008-01 | `PARTIAL` |
| F009 | 3.5, 4.9, 5.2 | MVP_SCOPE·API_CONTRACT·DATA_MODEL | AC-F009-01 | TC-F009-01 | `PARTIAL` |
| F010 | 4.4, 4.11, 5.2, 5.4 | MVP_SCOPE·ARCHITECTURE·DOMAIN_RULES·API_CONTRACT·DATA_MODEL·TEST_STRATEGY·ADR-0009·TASK-BACKEND-006 | AC-F010-01 | TC-F010-01·backend/tests/unit/test_auth_provider.py·backend/tests/scenarios/test_auth_provider_golden.py | `PARTIAL` |
| F011 | 4.1, 4.10, 4.11, 5.2 | MVP_SCOPE·API_CONTRACT·DATA_MODEL·DOMAIN_RULES·TEST_STRATEGY·ADR-0006·ADR-0010·TASK-BACKEND-007 | AC-F011-1-1~1-8 | TC-F011-1-1~1-8·backend/tests/unit/test_external_context.py·backend/tests/scenarios/test_external_context_golden.py | `DEFERRED` |
| F025 | 2.1, 2.4, 4.1, 4.4, 4.11, 5.2, 5.4 | MVP_SCOPE·API_CONTRACT·DATA_MODEL·DOMAIN_RULES·TEST_STRATEGY·IMPLEMENTATION_PLAN·ADR-0005 | AC-F025-01 | TC-F025-01 | `IMPLEMENTED` |
| F026 | 3.2, 3.3, 3.5, 4.5, 4.11, 5.2 | MVP_SCOPE·DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-F026-01 | TC-F026-01 | `IMPLEMENTED` |
| F027 | 3.5, 4.5, 4.7, 4.11, 5.2 | MVP_SCOPE·API_CONTRACT·DATA_MODEL | AC-F027-01 | TC-F027-01 | `IMPLEMENTED` |
| F028 | 보완-01, 4.7, 4.11, 5.2, 5.3 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-F028-01 | TC-F028-01 | `IMPLEMENTED` |
| F029 | 3.5, 4.6, 5.2 | MVP_SCOPE·API_CONTRACT·DATA_MODEL·TEST_STRATEGY·ADR-0007·ADR-0013(ACCEPTED 목표) | AC-F029-1-1~1-15 | TC-F029-1-1~1-15 | `IMPLEMENTED` |
| POL-001 | 3.5, 4.9, 5.2 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL001-01 | TC-POL001-01 | `IMPLEMENTED` |
| POL-002 | 4.9, 4.11, 5.2 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL002-01 | TC-POL002-01 | `IMPLEMENTED` |
| POL-003 | 3.5, 4.9, 4.11, 5.2 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL003-01 | TC-POL003-01 | `IMPLEMENTED` |
| POL-004 | 보완-01, 4.7, 5.2, 5.3 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL004-01 | TC-POL004-01 | `IMPLEMENTED` |
| POL-005 | 보완-01, 2.8, 4.7, 4.10, 5.2, 5.3 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL005-01 | TC-POL005-01 | `IMPLEMENTED` |
| POL-006 | 4.8, 4.9, 5.2 | API_CONTRACT·DATA_MODEL·TEST_STRATEGY | AC-POL006-01 | TC-POL006-01 | `IMPLEMENTED` |
| POL-007 | 3.2, 3.3, 3.4, 3.5, 4.5, 4.7, 5.2, 5.3 | DOMAIN_RULES·API_CONTRACT | AC-POL007-01 | TC-POL007-01 | `IMPLEMENTED` |
| POL-008 | 2.7, 3.2, 3.4, 3.7, 3.8, 5.3 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL008-01 | TC-POL008-01 | `IMPLEMENTED` |
| POL-009 | 2.1, 2.5, 4.4, 4.10, 4.11, 5.4 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL009-01 | TC-POL009-01 | `PARTIAL` |
| POL-010 | 2.1, 2.3, 2.4, 2.5, 2.8, 5.4 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL010-01 | TC-POL010-01 | `PARTIAL` |
| POL-011 | 2.4, 2.5, 4.4, 4.11, 5.4 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL·TEST_STRATEGY·ADR-0008·TASK-BACKEND-005 | AC-POL011-1-1~1-8 | TC-POL011-1-1~1-8 | `IMPLEMENTED` |
| POL-012 | 보완-03, 4.4, 5.4 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-POL012-01 | TC-POL012-01 | `IMPLEMENTED` |
| POL-013 | 1.3, 보완-04 | MVP_SCOPE·API_CONTRACT | AC-POL013-01 | TC-POL013-01 | `PARTIAL` |
| NFR-001 | 3.5, 4.6, 4.9, 5.2 | MVP_SCOPE·API_CONTRACT·DATA_MODEL | AC-NFR001-01 | TC-NFR001-01 | `IMPLEMENTED` |
| NFR-002 | 1.2, 5.1, 5.7 | TRACEABILITY | AC-NFR002-01 | TC-NFR002-01 | `PARTIAL` |
| NFR-003 | 3.4, 3.5, 3.8, 5.3 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL | AC-NFR003-01 | TC-NFR003-01 | `IMPLEMENTED` |
| NFR-004 | 2.1, 2.5, 3.5, 4.4, 5.4 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL·ADR-0008 | AC-NFR004-01 | TC-NFR004-01 | `IMPLEMENTED` |
| NFR-005 | 2.5, 4.4, 4.10, 4.11, 5.4 | DOMAIN_RULES·API_CONTRACT·DATA_MODEL·TEST_STRATEGY·ADR-0008 | AC-NFR005-01 | TC-NFR005-01 | `PARTIAL` |
| NFR-006 | 1.2, 3.7, 5.1, 5.2, 5.3, 5.7 | TRACEABILITY·TEST_STRATEGY | AC-NFR006-01 | TC-NFR006-01 | `IMPLEMENTED` |

F012~F023은 요구사항 정의서상 MVP 이후 확장 기능이다. 각 ID는 삭제·재사용하지 않고,
현재 MVP 완료율 계산과 구현 backlog에서 제외한다. 재개 시 별도 task 문서와 승인된 AC·TC를 먼저
만든 뒤 `MVP_EXCLUDED`에서 `PARTIAL`로 전환한다.

| 확장 ID | 범위 | WBS | 인수조건 | 테스트 | 상태 |
|---|---|---|---|---|---|
| F012 | 기능 제안 | 별도 확장 WBS 예정 | AC-F012-01 | TC-F012-01 | `MVP_EXCLUDED` |
| F013 | 영상 추천 | 별도 확장 WBS 예정 | AC-F013-01 | TC-F013-01 | `MVP_EXCLUDED` |
| F014 | 웰니스 코인 | 별도 확장 WBS 예정 | AC-F014-01 | TC-F014-01 | `MVP_EXCLUDED` |
| F015 | 혜택 교환 | 별도 확장 WBS 예정 | AC-F015-01 | TC-F015-01 | `MVP_EXCLUDED` |
| F016 | 운동용품 추천 | 별도 확장 WBS 예정 | AC-F016-01 | TC-F016-01 | `MVP_EXCLUDED` |
| F017 | 쇼핑 연결 | 별도 확장 WBS 예정 | AC-F017-01 | TC-F017-01 | `MVP_EXCLUDED` |
| F018 | 브랜드 캠페인 | 별도 확장 WBS 예정 | AC-F018-01 | TC-F018-01 | `MVP_EXCLUDED` |
| F019 | AI 상담 | 별도 확장 WBS 예정 | AC-F019-01 | TC-F019-01 | `MVP_EXCLUDED` |
| F020 | 에이전트 능력 활성화 | 별도 확장 WBS 예정 | AC-F020-01 | TC-F020-01 | `MVP_EXCLUDED` |
| F021 | 디지털 회복 에이전트 | 별도 확장 WBS 예정 | AC-F021-01 | TC-F021-01 | `MVP_EXCLUDED` |
| F022 | 집중 에이전트 | 별도 확장 WBS 예정 | AC-F022-01 | TC-F022-01 | `MVP_EXCLUDED` |
| F023 | 영양 에이전트 | 별도 확장 WBS 예정 | AC-F023-01 | TC-F023-01 | `MVP_EXCLUDED` |

### 3.4 세부 요구사항 추적 규칙

- 상위 그룹 행의 상태는 하위 세부 항목 중 가장 낮은 상태를 따른다. 상위 행만 `완료`로 표시하지 않는다.
- 세부 요구사항마다 WBS, 계약 문서 또는 API·데이터 필드, 인수조건, 테스트 케이스, owner를 연결한다.
- 요구사항 정의서의 ID와 문구는 임의로 합치거나 재사용하지 않는다. 범위가 바뀌면 새 세부 ID 또는 변경 기록을 추가한다.
- F002·F029의 AC/TC는 WBS 추적표의 세부 요구사항 ID를 그대로 사용한다. 상위 그룹 행의 범위 표기는 세부 ID 범위의 요약이며, 별도의 상위 AC/TC를 만들지 않는다.
- F002의 멀티 에이전트 구조는 공통 입력·기본 후보를 동일하게 받은 `TrainingAgent`, `RecoveryAgent`, `SafetyAgent`, `FeasibilityAgent`의 4개 proposal을 병렬 실행하고 `Coordinator`(의장)가 최종 통합하는 구조로 추적한다. `F002-1-10`, `F002-1-21`, `F002-1-26~50`, `F002-1-55~58`은 공통 입력·기본 후보, 각 Agent의 역할별 입력·출력, 실패, 저장, 최종 반영과 연결한다. `F002-1-22~25`는 제거된 별도 Safety 사전검사 단계의 기존 ID를 추적하기 위한 제외 항목이며, `F002-1-26~33`은 공통 기본 후보 준비·검증·저장을 추적한다.
- F029의 회의 UI는 `TrainingAgent`, `RecoveryAgent`, `SafetyAgent`, `FeasibilityAgent`, `Coordinator` 요약을 표시하되, `F029-1-13`에 따라 원래 루틴 선택 UI는 제공하지 않는다. 독립적인 최종 Safety 재검사 요약은 표시하지 않는다.
- `F002-1-51`, `F002-1-52`, `F002-1-56`에 따라 lighter·original은 공개 선택지로 추적하지 않고 내부 후보·SafetyAgent 의견 반영 기록으로만 관리한다.
- `F002-1-55~58`은 독립적인 최종 Safety 재검사가 아니라 SafetyAgent 의견의 Coordinator 반영 확인·근거 저장·거부 후보 처리를 추적한다.
- A2 이후 F002의 후속 AC/TC는 Round 1 proposal, canonical conflict, 영향 Agent의
  Round 2 review, constraint 단조성, Coordinator 결과와 additive persistence를 각각 추적한다.
  TASK-AGENT-002 A1은 승인된 계약 동결 작업일 뿐 기존 구현 상태를 `IMPLEMENTED`로 올리지 않는다.
- ACCEPTED ADR-0013 V3 목표의 F002 후속 AC/TC는 결정적 SafetyPolicyEngine·ConstraintEnvelope,
  ExercisePoolSnapshot, 세 LLM proposal, LangGraph routing, conflict/review, LLM Coordinator,
  Plan Compiler·integrity validator, deterministic fallback과 provider-free replay를 각각 추적한다.
- ACCEPTED ADR-0014의 F002 후속 AC/TC는 PostgreSQL eligible/mandatory filter, Qdrant ranking,
  PostgreSQL 재검증, mandatory 보존, Vector failure fallback과 catalog/collection/index/embedding replay를
  추가 추적한다.
- V3 재생성은 F002 후속 AC/TC로 root/parent lineage, 최대 두 번, idempotency, stale context,
  exact duplicate 거부와 meaningful difference를 추적한다. 신규 API·DB·frontend 구현 전에는
  `PARTIAL` 또는 미구현 목표 상태이며 기존 F029 `IMPLEMENTED` 증거를 V3 UI 완료로 해석하지 않는다.
- V3의 `SAFETY` 공개 요약은 historical API 호환 projection일 수 있지만 내부 Agent proposal이 아니다.
  SafetyPolicyEngine record와 세 Agent proposal을 별도로 추적한다.

## 4. PR 적용

각 기능 PR은 관련 행을 갱신하고 실제 테스트 파일이 생기면 테스트 ID 옆에 경로를 연결한다.
구현 착수 전 `docs/tasks/TEMPLATE.md` 기반 task 문서가 있어야 하며, 추상적인 제목이 아니라 실행
가능한 인수 조건, owner, API·DB 영향, 테스트 계획을 포함해야 한다. 계약만 있고 실행 코드나 테스트가
없는 경우 `PARTIAL` 또는 `DEFERRED`로 남기며 `IMPLEMENTED`로 올리지 않는다.

병합 시 task 문서와 이 표에 PR 번호, merge commit, 실제 테스트 결과를 기록한다. 기능 PR에서 이
갱신을 누락하면 NFR-002 추적성 인수 조건을 충족하지 못한다.

## 5. 대안과 선택 이유

스프레드시트 하나만 진실 공급원으로 사용하지 않는다. 원문 요구사항 ID는 보존하되 구현 계약과 테스트 링크는 저장소에서 함께 버전 관리한다.

## 6. 아직 확정되지 않은 사항과 질문

- F002의 60개 세부 AC를 코드 symbol과 테스트 함수 단위로 자동 검증하는 방식
- F003 웨어러블의 지원 제공자, scope, token vault, 원본·요약 품질·라이선스·보유기간
- F008의 고완료 시간대·운동유형·강도 패턴을 계산하기 위한 최소 데이터 기준
- F009를 결정적 주간 요약으로 종료할지 별도 AI 회고를 구현할지 여부
- F010 Google·Kakao·Naver 실제 출시 범위와 app·credential owner
- F011 캘린더 보류 해제 여부와 production OAuth client·redirect URI·secret-manager owner
- 체중 기반 예상 소모 칼로리 산식·version·단위·반올림 기준 또는 MVP 제외 결정
- POL-013 구독 결제·권한 전이의 MVP 포함 여부
- 447개 세부 요구사항 추적 검사를 CI에서 자동화할 시점
