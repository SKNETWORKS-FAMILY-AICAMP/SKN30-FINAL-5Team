# TEST_STRATEGY.md

## 1. 결정

테스트는 빠른 단위 테스트, 계약·DB 통합 테스트, 소수의 모바일 E2E, 안전 골든 시나리오로 구성한다. 안전 불변식과 결정 재현성은 일반 기능 테스트와 별도 suite로 고정한다.

현재 구현의 테스트 기준은 결정적 SafetyPolicyEngine → Safety-approved Pool → Training·Recovery·Feasibility 세 proposal → Coordinator → compiler → integrity validator다. integrity validator는 원시 안전을 재판정하지 않으며 compiled plan이 envelope를 위반하면 반드시 실패시킨다.

ADR-0012의 2라운드 구조화 상호검토는 승인된 V2 목표지만 아직 production 테스트 기준이 아니다.
A2/A3는 현재 V1 golden을 보존하면서 아래 V2 계약 suite를 별도로 통과해야 한다.

ADR-0013의 Safety-first LLM 멀티에이전트 V3 목표 계약은 `ACCEPTED`이며 별도 V3 suite와 shadow
비교가 production 전환 게이트다. ADR-0014 Qdrant retrieval은 `ACCEPTED`다. V3 계약 테스트가 현재
V1/V2 통과 증거를 대체하지 않는다.

## 2. 계층

| 계층 | 대상 | 주요 소유자 |
|---|---|---|
| Unit | 시간, 안전, 복귀, 후보, agent, coordinator | 개발팀장/데이터 |
| Repository | SQLAlchemy query, FK, transaction | 백엔드 |
| API | Pydantic, auth, status, idempotency, errors | 백엔드 |
| Contract | OpenAPI 하위 호환, frontend mock 일치 | 프론트 + 백엔드 |
| Component | 화면 상태, timer, 선택 불가, serious tone | 프론트 |
| Integration | API + PostgreSQL 전체 use case | 백엔드 |
| E2E | 모바일 핵심 흐름 | 전원 |
| Golden/Safety | 대표 입력의 action·제외·시간·veto | 개발팀장 + PM |

## 3. 필수 골든 시나리오

POL-009~013과 `ACCEPTED` ADR-0004에 연결된 정확한 보유기간·DORMANT·무료 체험 시나리오는 필수 production 게이트다.

1. 정상 상태는 원래 루틴 `KEEP`
2. 40분 상체·피로 MODERATE는 40분 요청과 CORE를 유지한 강도 `DOWNSHIFT`
3. 프로필 40분에서 사용자가 당일 30분으로 변경하면 30분을 사용하고 추가 축소하지 않음
4. 무릎 NRS 1–3/4–6은 검수된 금기 관계 운동을 제외하고, 4–6에는 `LIGHT` 상한을 추가
5. 무릎 NRS 7–10은 계획 없는 `REST`
6. 중대한 이상 반응은 계획 없는 `STOP_AND_SEEK_HELP`
7. 웨어러블 없음은 수동 체크인으로 정상 처리
8. 앱 운동 계획·세션에서 체중이 있으면 예상 소모 칼로리 추정치를 제공하고 체중이 없으면 값은 `null`
9. 칼로리 추정치가 진단·안전 판정의 단독 근거가 아님
11. LLM 실패는 동일 결정과 템플릿 설명
12. Safety envelope가 veto한 후보 또는 compiled plan 위반 후보가 최종 루틴으로 반환되지 않음
13. 필수 agent/provider 실패 시 결정적 fallback을 검증하고, 안전한 fallback이 없으면 `FAILED`, 계획 없음
14. 최초 가입자는 이전 리포트 없이 첫 주 목표·루틴을 생성
15. 모든 운동 블록 체크는 경과 시간과 무관하게 `COMPLETED`
16. 일부 블록 체크는 경과 시간과 무관하게 `PARTIAL`
17. 완료 블록이 없으면 경과 시간이 길어도 `NOT_COMPLETED`
18. 타이머 START/PAUSE/RESUME/END 이력이 상태를 변경하지 않음
19. 추가 운동 기록이 공식 블록 상태를 변경하지 않음
20. 닫힌 주 리포트 확인 전 다음 주 계획 확정 차단
21. 마지막 공식 완료 후 13일에는 일반 상태, 14일에는 복귀 모드이며 연속 미수행은 학습 신호만 생성
22. 계정 삭제 요청 즉시 접근 차단
23. 동의 철회 시 해당 동기화·토큰 즉시 중단
23-1. 가입 시 현재 서비스 이용약관 버전의 동의 이력이 저장되고 개인정보 consent 네 코드와 섞이지 않음
23-2. 개인정보처리방침은 열람 가능하지만 별도 consent code·동의 이력을 만들지 않음
24. 보유기간(28일/24시간/90일/12개월)과 관리자 로그 2년 검증
25. 가입 시 14일 AI 코치 무료 체험을 시작하고 Premium 결제는 노출하지 않음
26. Google·Kakao·Naver 로그인 선택과 인증 결과 처리
27. 웨어러블 동의·기기 선택·수면·걸음·활동시간·활동칼로리·운동 요약 저장
28. 웨어러블 미연동·권한 거부·API 오류가 실패 상태로 저장되고 수동 체크인·앱 블록 체크 경로가 유지됨
29. [MVP 이후] 수동 외부 운동 종류·시간·강도·체중 입력과 예상 칼로리의 `ESTIMATED/UNKNOWN/FAILED` 처리
31. 콜드스타트의 월요일~일요일 경계, 주간 목표 횟수, 특정 요일 비강제
32. 사용자 로컬 날짜 기준 만 18세가 되는 날과 만 64세인 사용자는 eligibility 통과
33. 만 18세 미만 또는 만 65세 이상은 `OUT_OF_SCOPE_AGE`로 일반 루틴 생성 차단
34. 미래·달력상 유효하지 않은 생년월일은 입력 오류로 거부
35. 범위 밖 결과는 상세 건강정보 추가 수집 없이 일반 루틴 생성이 차단됨
36. 범위 안 사용자는 다음 온보딩 단계로 진행
37. 생년월일·계산된 만 나이는 API 응답과 DB 평문에 없음
38. 생년월일 수정 시 서버가 사용자 로컬 날짜 기준으로 재검증하며 범위 밖 변경 시 일반 루틴 생성 차단
39. API 응답·로그·분석·LLM·에이전트·decision snapshot에 생년월일과 만 나이 미포함
40. 계정 삭제 시 암호화한 생년월일 삭제 대상 포함
42. 1년 이상 서비스 활동이 없는 계정의 `DORMANT` 분류와 삭제 30일 전 통지
43. 증상 사용자 시나리오에서 SafetyPolicyEngine의 `REVISE` envelope가 compiled plan에 유지되고 요청 운동 시간이 보존됨
44. 기존 클라이언트 구필드 호환 전략과 선택한 deprecation 또는 API 버전 전략의 프론트엔드·백엔드 호환성 테스트
45. 동일 입력·정책·카탈로그에서 SafetyPolicyEngine과 세 proposal 병렬 구조의 역할 분리·envelope 준수·요청 시간 보존을 검증함
46. ACTIVE 사용자 삭제 요청은 즉시 DELETION_PENDING과 단 하나의 request/job을 생성
47. 삭제 요청 직후 일반 인증 사용자 API와 외부 동기화를 차단
48. 같은 키와 새 키 재요청 모두 최초 request ID·deadline을 반환하고 새 job을 만들지 않음
49. job은 요청 즉시 실행할 수 있고 requested_at + 7일 전후 경계에서 운영 DB 삭제 기한을 판정
50. provider 실패는 기한 전 재시도하고 기한 후 로컬 삭제·backup 만료를 거쳐 COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE
51. 일부 repository 삭제 transaction 실패는 부분 commit 없이 실패 단계부터 재실행
52. 재실행은 완료 checkpoint를 건너뛰고 같은 policy version에서 같은 순서·대상을 사용
53. 사용자 연결 decision·proposal·feedback·생년월일·idempotency·cache/work payload 삭제
54. 재식별 가능 집계는 삭제하고 불가역 비식별 집계만 보존
55. opaque 감사·로그·snapshot에 사용자/provider 식별자, token, 원시 건강·오류가 없음
56. keyed-digest restore tombstone은 일치 backup 복원 계정을 차단하고 요청 후 30일에 만료
57. 마지막 관련 recovery point 만료 증적 전에는 deletion job COMPLETED 전이 금지
58. invalid state·nonce·PKCE 또는 만료·재사용 flow는 identity 조회 전에 거부
59. provider token issuer·audience 불일치, 만료·변조와 subject 누락은 user를 만들지 않음
60. provider timeout·5xx·rate limit은 retryable `PROVIDER_UNAVAILABLE`이고 원시 오류 비노출
61. 다른 user에 연결된 subject는 `IDENTITY_ALREADY_LINKED`이며 email 기반 자동 병합 없음
62. 같은 subject 반복 로그인은 같은 내부 user·identity를 재사용
63. provider 연결 해제 반복 호출은 이미 REVOKED일 때 성공 no-op
64. identity DB 저장 실패는 전체 rollback하고 custom token·성공 응답 없음
65. 마지막 활성 로그인 수단 일반 해제는 거부하고 account deletion 전체 해제는 허용
66. token·email·name·nickname·provider 원본 응답과 subject가 로그·snapshot·metric label에 없음
67. Google은 Firebase 기본 provider와 추가 scope 없음, Kakao/Naver 직접 adapter는 `openid`만 허용
75. [V3] SafetyPolicyEngine이 `STOP_AND_SEEK_HELP` 또는 생성 금지 veto를 확정하면 LLM Agent와
    Coordinator를 호출하지 않고 plan을 반환하지 않음
76. [V3] Training·Recovery·Feasibility 세 LLM Agent가 같은 envelope·pool hash로 병렬 실행되고
    완료 순서와 무관하게 canonical proposal ordering을 가짐
77. [V3] Agent가 pool 밖 exercise ID를 반환하면 structured output을 거부하고 부분 proposal로
    Coordinator를 실행하지 않음
78. [V3] repairable duration/ceiling/schema 위반은 Coordinator를 정확히 한 번 repair하고 재검증함
79. [V3] non-repairable veto·필수 입력·정책 데이터 오류와 repair 재실패는 Coordinator로 돌아가지 않음
80. [V3] provider 전체 장애는 같은 envelope를 만족하는 deterministic fallback을 검증해 반환하거나
    안전한 fallback이 없으면 계획 없는 `FAILED`임
81. [V3] 수동 재생성은 추가 사용자 입력 없이 같은 유효 snapshot·envelope·pool에서 세 Agent부터
    시작하고 이전 plan과 의미 있게 다름
82. [V3] 재생성 exact duplicate와 설명·UUID·미미한 시간만 다른 plan은 거부함
83. [V3] 재생성 성공 1·2회는 허용하고 세 번째는 `REGENERATION_LIMIT_REACHED`이며 idempotent함
84. [V3] stale envelope·pool 또는 version mismatch는 `REGENERATION_CONTEXT_STALE`이고 LLM을 호출하지 않음
85. [V3/Vector] Safety veto·REST·STOP_AND_SEEK_HELP에서는 Qdrant 호출이 0회임
86. [V3/Vector] PostgreSQL eligible allowlist 밖 Qdrant ID와 stale/non-canonical row는 제거되고
    `VECTOR_RESULT_NOT_CANONICAL` 또는 `VECTOR_RESULT_STALE`을 기록함
87. [V3/Vector] mandatory 목표 운동과 승인 안전 대체는 Vector top-k 누락에도 snapshot에 보존됨
88. [V3/Vector] unavailable/not-ready/timeout/index-version mismatch는 같은 envelope의 deterministic
    pool fallback과 stable hash를 만들거나 안전한 pool이 없으면 계획 없이 종료함
89. [V3/Vector] stored retrieval request/result와 catalog/collection/index/embedding/graph/prompt/model
    version으로 Qdrant/provider 재호출 없이 replay함
90. [Daily Check-in pain] false/empty, true/non-empty, 부위 중복 금지와 모든 NRS 1..10 점수
    필수를 검증함
91. [Daily Check-in pain] NRS 경계 1/3/4/6/7/10의 severity 변환과 policy version 저장을 검증함
92. [Feedback] 신규 difficulty-only와 legacy request 양쪽을 호환 기간에 수용하고 historical field를
    삭제·false backfill하지 않음
93. [Weekly pain] safety-event distinct session을 집계하고 legacy feedback과 중복하지 않으며 onboarding/
    daily pain은 `pain_report_count`에 포함하지 않음

## 4. 속성·불변식 테스트

- 사용자의 USER_OVERRIDE 없이 `requested_duration_minutes`가 바뀌지 않음
- 최종 루틴이 사용자의 requested duration을 보존함
- plan이 있는 최종 루틴의 `estimated_duration_seconds`가 `requested_duration_minutes * 60`의 ±300초 이내이며 허용 후보 중 차이가 가장 작음
- estimated duration과 actual elapsed time이 완료 상태에 영향을 주지 않음
- 운동 블록 완료 mutation의 중복 요청이 한 번만 반영됨
- 완료 취소는 세션 종료 전에만 PENDING으로 되돌릴 수 있음
- 종료된 COMPLETED/PARTIAL/NOT_COMPLETED 세션과 STOPPED_SAFETY 실행 세션은 변경할 수 없음
- 다음 운동은 sequence상 첫 PENDING 블록임
- `PAIN_OR_ABNORMAL_RESPONSE` 안전 중단은 증상 세부정보 없이 세션 전체를 종료하고 당일 이어하기·Alternative를 차단함
- `persistent_pains`는 Daily Check-in에 기본값으로만 표시되며, 사용자가 당일 값을 제출하기 전에는 Safety 입력으로 사용되지 않음
- Safety Event 결과는 완료 블록 수 기반 공식 수행 상태와 별도 저장됨
- REST/STOP 응답에는 plan 없음
- REST 선택 당일에는 추가 압박 알림을 보내지 않음
- 복귀 모드는 마지막 공식 COMPLETED 후 14일 공백으로만 활성화됨
- NOT_COMPLETED 이력은 복귀 트리거·벌점이 아닌 학습 신호임
- 복귀 모드에서 승인된 load/volume cap port가 없거나 미승인이면 계획을 fail-closed 처리함
- 승인된 복귀 cap 적용 전후 requested duration이 정확히 보존됨
- IANA timezone별 동일 instant를 사용자 로컬 날짜로 변환해 월요일 00:00~다음 월요일 00:00 경계를 판정함
- 열린 주는 최종 report 생성을 차단하고, 닫힌 주만 불변 최소 집계 입력을 허용함
- GENERATED report는 다음 계획 finalize를 차단하고 명시적 ACKNOWLEDGED 뒤에만 허용함
- 첫 사용자 주에 cold_start가 명시되고 직전 report가 없는 경우만 acknowledgement 예외를 허용함
- INITIAL은 초기 계획 흐름, AI/USER는 revision 흐름에서만 생성함
- 성공한 Coordinator 기반 AI revision 1·2회는 허용하고 3회는 차단하며 비성공 상태는 횟수를 늘리지 않음
- NEEDS_INPUT/BLOCKED/FAILED revision은 routine이 없고 finalize할 수 없음
- USER 편집은 요청 시간·장소·Safety envelope와 compiled-plan integrity를 모두 준수함
- LLM은 weekly routine·안전 상태·veto·후보를 변경하지 않음
- 같은 weekly aggregate/revision 입력과 policy version은 같은 판정 결과를 만듦
- 승인되지 않은 exercise/rule/alternative가 plan에 없음
- SafetyPolicyEngine 결과, Training PlanSpec, Recovery·Feasibility adjustment code와 final decision이 분리되고 Coordinator가 최종 루틴 한 개를 선택한다.
- 증상 사용자 시나리오에서 SafetyPolicyEngine envelope와 compiled-plan integrity validator를 강제하며, `NEEDS_INPUT`과 `FAILED`는 계획을 반환하지 않는 fail-closed 결과로 처리한다.

ADR-0012 V2의 필수 속성·불변식 (SUPERSEDED, ADR-0015로 대체됨. 결정 기록으로만 보존한다):

- no-conflict 입력은 Round 2 Agent를 호출하지 않고 `SKIPPED_NO_CONFLICT`이며, 네 Agent 모두
  `NOT_REQUIRED` event를 가지고 V1과 같은 최종 결과다.
- conflict code, review 대상, proposal/review hash는 실행 완료 순서와 무관하게 canonical하다.
- 비대상 Agent는 누락이 아니라 `NOT_REQUIRED` review event를 가진다.
- 대상 review 누락·FAILED는 decision FAILED, NEEDS_INPUT은 계획 없는 NEEDS_INPUT이다.
- Safety veto는 `false -> true`만 가능하고 `true -> false`는 모든 입력 조합에서 거부된다.
- Safety 제외 운동은 Round 2에서 제거되지 않고 추가 방향만 허용된다.
- 요청 시간·시간 출처·승인 후보 집합·입력/정책/카탈로그/규칙 버전은 Round 2 전후 동일하다.
- Feasibility hard constraint와 승인된 Recovery ceiling은 Training preference로 완화되지 않는다.
- 모든 hard constraint와 Training 목표를 만족하는 후보가 없으면 목표·시간을 바꾼 성공 plan이 없다.
- 동일 입력·모든 버전은 동일 conflict, review, candidate와 final action을 만든다.
- LLM 비활성·실패·출력 거부는 conflict/review/final 결과를 바꾸지 않고 전체 템플릿을 사용한다.
- review/LLM payload에 직접 식별자, 날짜, 자유 체크인, 원시 건강·웨어러블, application log가 없다.
- constraint integrity validator는 Safety 규칙을 재실행하거나 독립 FinalSafetyGate 결과를 만들지 않는다.

ADR-0013 V3의 필수 속성·불변식:

- SafetyPolicyEngine 출력과 ConstraintEnvelope는 세 Agent, Coordinator, repair와 regeneration에서
  완화되거나 version/hash가 바뀌지 않는다.
- ExercisePoolSnapshot은 production-approved catalog row만 포함하고 canonical order/hash를 가지며
  모든 LLM exercise reference는 pool의 부분집합이다.
  application log, prompt 원문과 provider 예외 원문이 없다.
- Agent와 Coordinator는 DB·repository·ORM·raw SQL Tool을 등록하거나 호출하지 않는다.
- 세 Agent의 fan-out은 병렬이며 fan-in 전 누락·invalid·timeout 결과로 Coordinator를 실행하지
  않는다.
- ADR-0015: Training만 `exercise_prescriptions`를 반환한다. Recovery와 Feasibility가 계획을 제출하면
  계약이 거부한다.
- ADR-0015: Coordinator 앞에 결정론적 관문이 없다. Coordinator 출력에 대한 검사는 compiled plan을
  대상으로 하는 integrity validator 하나이며, 이 검사만으로 Safety veto가 유지되는지 확인한다.
- ADR-0015: Recovery·Feasibility의 `adjustment_codes`는 권고이므로, 반영되지 않았다는 이유로
  결정이 실패하지 않는다.
- Coordinator initial/repair output은 Pydantic schema, pool membership와 envelope constraint를 통과해야
  하고 repair attempt는 0 또는 1뿐이다.
- Plan Compiler 산술은 deterministic하고 plan 구성요소 합계가 requested duration의 허용 범위
  (`DURATION_TOLERANCE_SECONDS`) 안에 든다.
- 최종 validator는 원시 Safety 분류를 재실행하지 않고 envelope 준수 assertion만 수행한다.
- `STOP_AND_SEEK_HELP`는 REST, fallback plan 또는 Coordinator repair로 바뀌지 않는다.
- deterministic fallback도 compiler와 같은 integrity validator를 통과해야 final option이 된다.
- regeneration은 root/parent/sequence lineage를 보존하고 exact duplicate를 거부하며 네 meaningful
  difference code 중 하나 이상을 갖는다.
- 같은 Idempotency-Key는 같은 regeneration response를 반환하고 다른 payload 재사용은 409다.
- stored envelope·pool·proposal·Coordinator output·compiler/validation과 version으로 provider
  재호출 없이 같은 final result를 replay한다.
- LangGraph persistent checkpoint와 외부 trace 전송은 초기 V3에서 발생하지 않는다.
- PostgreSQL이 eligible/mandatory ID를 먼저 계산하고 Qdrant는 eligible 범위의 순위·다양성만 결정한다.
- Qdrant 결과는 같은 catalog version의 PostgreSQL 재검증 뒤에만 snapshot에 들어간다.
- mandatory 목표 운동과 승인 안전 대체는 Vector 결과와 무관하게 보존된다.
- Agent와 Coordinator dependency graph에는 repository/Qdrant port나 client가 없다.
- 통증 부위·점수, 직접 식별자와 raw health/wearable 값은 vector/payload/embedding query/log에 없다.

안전 상태와 API 결과의 매핑은 다음과 같다.

| 상태 | API 결과 | 계획 |
|---|---|---|
| `NEEDS_INPUT` | `422 NEEDS_INPUT` | 반환하지 않음 |
| `FAILED` | `500/503 DECISION_FAILED` | 반환하지 않음 |
| `BLOCKED` | 정상 `DecisionResponse` | `REST` 또는 `STOP_AND_SEEK_HELP`, 계획 없음 |
| `PASS` | 정상 `DecisionResponse` | 운동 계획 반환 |
| `REVISE` | 정상 `DecisionResponse` | 조정된 운동 계획 반환 |

- Training은 목표·진행 PlanSpec, Recovery는 회복·부하 adjustment code, Feasibility는 시간·장소·일정 adjustment code를 추적하고, SafetyPolicyEngine envelope와 Coordinator 최종 결정을 별도 추적한다.
- 동일 입력·버전에서 세 proposal 병렬 구조, Safety envelope 및 compiled-plan integrity 결과를 비교한다.
- 같은 입력 해시와 버전은 같은 후보와 action
- client가 rule version이나 agent weight를 지정할 수 없음
- 안전 상태가 PASS/REVISE가 아닌 최종 루틴은 반환·선택 불가
- `date_of_birth`가 유효한 `YYYY-MM-DD`이며 온보딩 필수이고, 만 나이는 사용자 로컬 날짜 기준으로 일시 계산되며 DB에 저장되지 않음
- agent proposal과 final decision이 분리되고 내부 추론이 노출되지 않음
- 계정 삭제의 7일은 job 실행 대기기간이 아니라 운영 DB hard-delete 완료 상한임
- ACTIVE에서 DELETION_PENDING 전이와 최초 deletion request/job 생성은 하나의 transaction임
- DELETION_PENDING 사용자의 일반 제품 API는 차단되고 deletion lifecycle 멱등 재요청만 허용됨
- 같은 사용자에게 활성 deletion request/job은 하나이며 새 idempotency key도 최초 receipt를 재사용함
- 삭제 단계는 ACCESS_BLOCK, EXTERNAL_REVOCATION, OPERATIONAL_DATA_DELETE,
  CACHE_AND_WORK_DELETE, AUDIT_DEIDENTIFICATION, BACKUP_EXPIRY_VERIFICATION의 고정 prefix임
- 재실행은 성공 checkpoint를 반복하지 않고 실패 단계부터 재개함
- provider 해제 실패가 로컬 사용자 연결 데이터의 7일 이상 보유 근거가 되지 않음
- provider 최종 실패 경로의 backup 완료 상태는 COMPLETED_WITH_EXTERNAL_REVOCATION_FAILURE임
- 운영 DB hard delete 실패는 FAILED_REQUIRES_REVIEW이며 성공이나 접근 복구로 매핑되지 않음
- 계정 삭제는 일반 데이터별 보유기간보다 우선하고 가명·재식별 가능 집계를 삭제함
- opaque 감사 field allowlist에 user/provider ID, 생년월일, token, idempotency key, 원시 payload가 없음
- restore-block tombstone은 HMAC-SHA256 keyed digest만 저장하며 key는 row·로그·fixture에 없음
- tombstone은 requested_at + 30일을 넘겨 보존하지 않고 opaque 감사 TTL은 승인된 retention
  policy 없이는 하드코딩되지 않음
- backup expiry 증적이 없으면 단순 시간 경과만으로 COMPLETED를 만들지 않음
- Firebase subject와 provider subject는 별도 principal/identity로 취급하고 같은 값으로 추정하지 않음
- 활성 `(provider_code, provider_subject)`와 Firebase principal subject는 각각 전역 unique임
- email·name·nickname·phone·birthday·profile claim은 identity 조회·생성·병합 입력이 아님
- direct OAuth flow는 UUIDv4, 10분 TTL, state/nonce digest, PKCE S256 challenge만 저장함
- raw authorization code·state·nonce·verifier와 모든 token은 영속화되지 않음
- Google Firebase 경로는 backend direct exchange route를 호출하지 않음
- Kakao는 state·nonce·PKCE S256, Naver는 state·PKCE S256을 적용하고 미문서 nonce를 추정하지 않음
- 독립 identity unlink는 총 5회·24시간 예산 뒤 REVIEW 상태이며 account deletion은 ADR-0008을 따름
- 로컬 자정 경계와 DST 23/25시간 날짜를 UTC instant로 정확히 처리함

## 5. 테스트 데이터

- 합성 UUID와 가상 프로필만 사용한다.
- 실제 이메일, 토큰, 이름, 건강 기록을 fixture에 넣지 않는다.
- raw reference data는 unit fixture로 직접 쓰지 않고 승인된 최소 normalized seed를 사용한다.
- 골든 결과는 policy/catalog/ruleset version과 함께 저장한다.

### 5.1 Weekly policy 골든 계약

주간 골든 fixture는 합성된 IANA timezone, 월요일·일요일 경계, 네 공식 세션 상태의 최소
집계, acknowledgement 상태, revision source, 성공한 AI revision 횟수, 요청 시간·장소와
포함하지 않는다.

골든 비교 축은 OPEN/CLOSED, report 허용 여부, 학습 신호와 penalty 미적용, revision 허용 여부,
AI revision 결과 횟수, routine 허용 여부, finalized와 policy/schema version이다. 설명 문구나 LLM
출력은 비교 입력 또는 결정 결과에 포함하지 않는다.

### 5.2 Decision 골든 계약

Wave 6의 decision 저장·API 매핑 테스트는
`backend/tests/scenarios/decision_golden_fixtures.py`의 버전화된 fixture를 기준으로 한다.
각 case는 catalog, policy, safety rule, duration rule, graph, coordinator와 proposal schema
version을 모두 명시한다. 합성된 정규화 context reference만 사용하며 직접 식별자, 생년월일,
만 나이, 토큰과 원시 건강·웨어러블 데이터는 포함하지 않는다.

전문 Agent proposal 기대값과 Coordinator final result 기대값은 별도 레코드로 비교한다.
골든 결과 비교의 필수 축은 status, action, selected candidate, safety status, reason code,
blocked reason code, requested duration, duration adjustment source와 estimated duration이다.
자유 형식 summary·guidance·LLM 문구는 결정 재현성 비교에 포함하지 않는다. LLM 미사용과
설명 생성 실패는 같은 입력·version에서 동일한 결정 결과를 만들어야 한다.

현재 저장 계층은 SafetyPolicyEngine 결과와 세 proposal을 별도 레코드로 저장하고 final result와 덮어쓰거나
합치지 않는다. 공개 API 매핑은 기존 `API_CONTRACT.md` 필드만 사용하며 fixture의
`graph_version` 등 내부 감사 version을 임의로 공개 필드로 추가하지 않는다.

### 5.3 Decision 재현성 통합 게이트

저장 전 domain 경계는 식별자가 없는 최소 input snapshot과 별도 proposal·candidate,
catalog/policy/safety/duration/graph/coordinator version 조합을 사용해 Coordinator 입력을
복원할 수 있어야 한다. input hash 기준은 UTF-8 canonical JSON(sorted object key, compact
separator)의 SHA-256이다. 집합 의미의 context reference 순서는 hash에 영향을 주지 않지만,
운동 sequence처럼 의미 있는 배열 순서는 임의로 정렬하지 않는다.

조회 후 재실행 결과는 저장된 action, selected candidate, safety status, reason code와 duration
결과에 일치해야 한다. 세 proposal은 agent별로 분리되어야 하며 누락·중복·FAILED를 성공
결정으로 복원할 수 없다. Safety `BLOCKED` 또는 veto 결과에는 `FINAL_ROUTINE` option을
연결할 수 없고, 저장 transaction이 실패하면 성공 응답을 공개할 수 없다.

`feat/decision-api-persistence`가 제공되기 전에는 위 항목을 domain-level replay contract로
검증한다. 실제 SQLAlchemy round trip, transaction rollback, idempotency, 조회 API와
`NEEDS_INPUT`/`DECISION_FAILED` HTTP 매핑은 backend 소유 integration suite에서 같은 골든
fixture를 사용해 추가 검증해야 한다.

### 5.3.1 [V3 목표] LLM graph, Vector retrieval replay와 regeneration 계약

V3 replay fixture는 input, ConstraintEnvelope, ExercisePoolSnapshot, 세 structured proposal,
Coordinator initial/repair output, compiled plan, validation result와 모든 version/hash를 분리한다.
replay는 provider를 mock으로도 호출하지 않고 저장된 structured output에서 final result를 복원한다.

ADR-0014 fixture는 eligible/mandatory ID, retrieval request/result, collection/index/embedding/query version,
Qdrant ranked ID·score, PostgreSQL revalidation, fallback code/version과 pool hash를 분리한다. privacy
fixture는 통증 부위·점수, user identifier와 raw health/wearable 값이 vector/payload/query/log에 없는지
allowlist로 검증한다.

fresh LLM inference의 byte-identical 결과는 재현성 기준이 아니다. 대신 schema/pool/constraint 위반율,
deterministic fallback율, expert agreement, safety invariant 100%, p50/p95 latency와 decision당 비용을
V1 shadow 결과와 비교한다.

V3-C1의 offline harness는 `backend/app/modules/decisions/v3_evaluation.py`와 versioned synthetic fixture
20개를 사용한다. 기본 CLI는 저장된 `V3ShadowExecutionResult`만 읽어 provider를 0회 호출하며 결과·요약·
전문가 검토 template·manifest를 생성한다. 명시적 safety/constraint violation만 hard gate이고 latency,
cost, fallback, structured-output, review/repair와 expert agreement threshold는 V3-C2 승인 전 report-only다.
전문가 검토가 없거나 token/pricing 근거가 불완전하면 0으로 대체하지 않고 `NOT_REVIEWED` 또는 `null`로
남긴다. 상세 실행·report schema와 해석 기준은 `docs/runbooks/v3-shadow-evaluation.md`를 따른다.

V3-C2의 `v3_promotion.py`는 승인된 versioned threshold JSON이 있을 때만 C1 evidence를 평가한다.
manifest file hash·record count, summary/result 내부 hash, fixture/harness/graph/policy/catalog/prompt/provider/
model version, completed expert review와 pricing 정합성을 다시 검증한다. safety invariant 100%, veto override
0건과 constraint violation 0건은 threshold가 완화할 수 없는 hard gate다. nullable latency/token/cost/review
metric은 0으로 추정하지 않으며 필요한 값이 unavailable이면 canonical reason code와 `BLOCKED`를 반환한다.
동일 입력은 stable decision hash와 byte-stable JSON을 만든다. `READY_FOR_HUMAN_APPROVAL`은 자동 production
승인이 아니며 feature flag를 변경하지 않는다. 상세 절차는 `docs/runbooks/v3-production-promotion.md`를
따른다.

regeneration fixture는 원본과 최대 두 개의 child run, idempotency key, 이전/new plan hash와 meaningful
difference code를 포함한다. stale TTL·version mismatch, exact duplicate, 대안 없음과 concurrent sequence
충돌을 각각 검증한다.

backend API 경계는 `backend/tests/api/test_decision_regenerations.py`에서 request/header validation,
application port 단일 호출, lineage/engine/difference projection, stable error mapping, 기본 feature 비활성,
V1/V2 response field 호환성을 검증한다. locking·동시성·실패 attempt와 성공 sequence 계산은 route가
아니라 후속 regeneration application/repository integration suite의 책임이다.

### 5.4 Account deletion 골든·개인정보 계약

계정 삭제 골든 fixture는 합성 UUIDv4, timezone-aware 시각, provider 성공·실패 machine code,
고정 stage checkpoint와 `account-deletion-policy-v1`만 사용한다. 이메일, 이름, 생년월일,
Firebase/provider subject, token, 실제 건강·웨어러블 값은 fixture에 포함하지 않는다.

domain unit은 즉시 접근 차단, 새 키 resource-level 멱등성, 7일/30일 경계, provider 최종 실패,
retention 분류, HMAC tombstone과 opaque 감사 allowlist를 검증한다. golden scenario는 부분 실패,
재실행, decision/proposal/feedback 삭제, 비식별 집계 구분과 backup 증적 gate를 검증한다.

실제 SQLAlchemy 구현 PR은 동일 contract에 repository transaction rollback, FK delete graph,
동시 요청 unique, Alembic round trip과 PostgreSQL integration test를 추가해야 한다. 실제 provider,
scheduler/queue, AWS backup 리소스는 adapter·운영 task로 분리한다.

### 5.5 Auth provider 골든·보안 계약

인증 provider fixture는 합성 UUIDv4, 고정 timezone-aware 시각, provider·failure machine code와
`auth-provider-policy-v1`과 `identity-social-v1`만 사용한다. 실제 authorization code, access/refresh/ID/custom token,
state, nonce, verifier, Firebase/provider subject, email, name, nickname과 provider 원본 응답은
fixture·snapshot에 포함하지 않는다. subject가 필요한 검증은 의미 없는 합성 문자열만 메모리에서
사용하고 로그·snapshot 기대값에는 포함하지 않는다.

domain unit은 Google Firebase 경로, provider별 허용 scope, state/nonce/PKCE, issuer/audience/
signature/expiry/subject, 반복 identity 해석, 충돌, 해제 retry와 observability allowlist를 검증한다.
golden suite는 필수 10개 시나리오인 invalid state/nonce, issuer/audience 불일치, 만료·변조 token,
timeout/5xx, subject 누락, subject uniqueness 충돌, 반복 로그인, 연결 해제 반복, DB rollback,
token·profile·원본 응답 비노출을 고정한다.

Kakao 첫 adapter PR은 authorize-init 10/11·60/61 fixed-window 경계, 600초 만료, provider 호출 전
digest row 소비·삭제, 실패 시 새 init, verifier ownership, OIDC verifier·service·API tests,
PostgreSQL concurrent unique/rollback, additive Alembic round trip과 frontend callback contract를 추가한다. 실제 adapter test는
official discovery/JWKS에서 만든 최소 합성 fixture와 합성 HTTP failure를 사용하며 live provider나 실제
credential을 CI 필수 조건으로 만들지 않는다. Google은 기존 Firebase 경로를 유지하고 Naver는 후속 독립 PR이다.

## 6. CI 게이트

구현 단계에서 다음 job을 독립 실행하도록 구성한다.

- docs/link/contract static checks
- backend format/lint/type/unit
- backend API/integration with PostgreSQL
- safety golden/fallback/reproducibility
- [V3] LangChain structured output, LangGraph routing, privacy payload, replay와 regeneration contract
- [V3-C1] shadow/public gate 독립, OpenAI factory fail-closed, full audit artifact, provider usage와
  versioned pricing, synthetic JSONL privacy contract
- [V3/Vector] Qdrant adapter contract, PostgreSQL revalidation, deterministic fallback와 privacy/replay
- frontend format/lint/type/component/build
- migration up/down 또는 forward-fix validation

V3-C1 CI는 fake `BaseChatModel`만 사용한다. live OpenAI 호출과 실제 key는 CI 필수 조건이 아니다.
Safety veto/생성 금지는 provider·Qdrant zero-call, Specialist 일부 실패는 Coordinator zero-call,
repair는 최대 한 번이어야 한다. 실제 shadow 결과 수집, latency/cost threshold 판정과 expert review는
harness 구현 완료와 구분해 후속 staging evidence로 남긴다.

백엔드 기반 명령은 TASK-BACKEND-001에서 아래와 같이 확정한다. 프론트엔드 명령은 해당 초기화 PR에서 확정한다. 실행하지 않은 테스트를 통과로 보고하지 않는다.

### Python 린터와 타입 체커

TASK-DATA-001의 Python 린터·포매터는 ruff, 타입 체커는 mypy로 선택했다. 설정과 고정
버전은 해당 코드와 함께 루트 `pyproject.toml`로 통합한다. `pyproject.toml`이 아직 없는
브랜치에서는 아래 명령을 계획된 게이트로만 취급하고 실행됐다고 보고하지 않는다. 초기 검사
범위는 `data/scripts`이며, backend 코드가 추가되면 같은 설정을 확장한다.

```powershell
uv sync --frozen --group dev
uv run ruff check backend data/scripts
uv run ruff format --check backend data/scripts
uv run mypy
uv run pytest
uv run python -m unittest discover -s data/scripts/tests
```

Pyright를 선택하지 않은 이유는 저장소의 Python 산출물이 표준 라이브러리 기반이고 CI에서
ruff와 동일한 Python 툴체인으로 실행하는 편이 단순하기 때문이다. 프론트엔드 타입 검사는
이 결정과 무관하다.


## 7. 대안과 선택 이유

E2E만으로 검증하지 않는다. 원인 파악이 느리고 안전 규칙의 모든 조합을 다루기 어렵다. snapshot만으로 agent 결과를 고정하지 않고 구조 필드와 도메인 불변식을 함께 검증한다.

## 8. 아직 확정되지 않은 사항과 질문

- React Native E2E 도구
- 성능 목표와 부하 테스트 임계값
- 외부 도메인 검수자가 승인할 골든 결과 형식
