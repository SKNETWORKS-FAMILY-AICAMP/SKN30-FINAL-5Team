# TEST_STRATEGY.md

## 1. 결정

테스트는 빠른 단위 테스트, 계약·DB 통합 테스트, 소수의 모바일 E2E, 안전 골든 시나리오로 구성한다. 안전 불변식과 결정 재현성은 일반 기능 테스트와 별도 suite로 고정한다.

현재 멀티 에이전트 기준은 [ADR-0007](adr/0007-multi-agent-structure-correction.md)에 따른 Training·Recovery·Safety·Feasibility 네 proposal의 병렬 실행과 Coordinator의 최종 결정이다. 증상 사용자 시나리오에서 SafetyAgent 의견 반영 수준을 확인하며, 결과에 따른 후속 수정 가능성은 열어 둔다. 독립적인 최종 Safety 재검사는 현재 테스트 범위에 포함하지 않는다.

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
| Requirement | 칼로리 추정·동의·보유기간·캘린더·웨어러블·콜드스타트 | 백엔드 + 기획PM |

## 3. 필수 골든 시나리오

POL-009~013과 `ACCEPTED` ADR-0004에 연결된 정확한 보유기간·DORMANT·무료 체험 시나리오는 필수 production 게이트다.

1. 정상 상태는 원래 루틴 `KEEP`
2. 40분 상체·피로 MODERATE는 40분 요청과 CORE를 유지한 강도 `DOWNSHIFT`
3. 프로필 40분에서 사용자가 당일 30분으로 변경하면 30분을 사용하고 추가 축소하지 않음
4. 무릎 MILD/MODERATE는 검수 충돌 제외와 대체
5. 무릎 SEVERE는 계획 없는 `REST`
6. 중대한 이상 반응은 계획 없는 `STOP_AND_SEEK_HELP`
7. 웨어러블 없음은 수동 체크인으로 정상 처리
8. 앱 운동 계획·세션에서 체중이 있으면 예상 소모 칼로리 추정치를 제공하고 체중이 없으면 값은 `null`
9. 칼로리 추정치가 진단·안전 판정의 단독 근거가 아님
10. 캘린더는 등록된 운동 일정의 수행 여부만 확인하고 세부 운동 기록을 저장하지 않으며 공식 운동 수행 상태를 변경하지 않음
11. LLM 실패는 동일 결정과 템플릿 설명
12. 안전 veto된 후보가 최종 루틴으로 반환되지 않음
13. 필수 agent 하나 실패 시 decision `FAILED`, 계획 없음
14. 최초 가입자는 이전 리포트 없이 첫 주 목표·루틴을 생성
15. 모든 운동 블록 체크는 경과 시간과 무관하게 `COMPLETED`
16. 일부 블록 체크는 경과 시간과 무관하게 `PARTIAL`
17. 완료 블록이 없으면 경과 시간이 길어도 `NOT_COMPLETED`
18. 타이머 START/PAUSE/RESUME/END 이력이 상태를 변경하지 않음
19. 추가 운동 기록이 공식 블록 상태를 변경하지 않음
20. 닫힌 주 리포트 확인 전 다음 주 계획 확정 차단
21. 7일 또는 3회 미수행 복귀 모드
22. 계정 삭제 요청 즉시 접근 차단
23. 동의 철회 시 해당 동기화·토큰 즉시 중단
24. 보유기간(28일/24시간/90일/12개월)과 관리자 로그 2년 검증
25. 가입 시 14일 AI 코치 무료 체험을 시작하고 Premium 결제는 노출하지 않음
26. Google·Kakao·Naver 로그인 선택과 인증 결과 처리
27. 웨어러블 동의·기기 선택·수면·걸음·활동시간·활동칼로리·운동 요약 저장
28. 웨어러블 미연동·권한 거부·API 오류가 실패 상태로 저장되고 수동 체크인·앱 블록 체크 경로가 유지됨
29. [MVP 이후] 수동 외부 운동 종류·시간·강도·체중 입력과 예상 칼로리의 `ESTIMATED/UNKNOWN/FAILED` 처리
30. 캘린더 동의·권한, 빈 시간 후보, 운동 계획 등록·수행 여부 확인과 연동 실패 시 계획 보존
31. 콜드스타트의 월요일~일요일 경계, 주간 목표 횟수, 특정 요일 비강제
32. 사용자 로컬 날짜 기준 정확히 만 14세가 되는 날 가입 허용
33. 만 14세가 되기 하루 전이면 `만 14세 미만은 이용할 수 없습니다` 안내 후 가입 차단
34. 미래·달력상 유효하지 않은 생년월일은 입력 오류로 거부
35. 만 14세 미만 안내 후 다음 화면으로 진행되지 않음
36. 만 14세 이상은 별도 연령 안내 없이 다음 화면으로 이동
37. 프로필에 서버가 계산한 만 나이만 표시되고 DB에는 저장하지 않음
38. 생년월일 수정 시 서버가 사용자 로컬 날짜 기준으로 재검증하며 만 14세 미만 변경 시 이용 차단
39. API 응답·로그·분석·LLM·에이전트·decision snapshot에 생년월일과 만 나이 미포함
40. 계정 삭제 시 암호화한 생년월일 삭제 대상 포함
41. 캘린더 동의 철회 시 동기화 중단과 비연동 경로 유지
42. 1년 이상 서비스 활동이 없는 계정의 `DORMANT` 분류와 삭제 30일 전 통지
43. 증상 사용자 시나리오에서 SafetyAgent의 `REVISE` 의견이 Coordinator 최종 결정에 반영되고 요청 운동 시간이 보존됨
44. 기존 클라이언트 구필드 호환 전략과 선택한 deprecation 또는 API 버전 전략의 프론트엔드·백엔드 호환성 테스트
45. 동일 입력·정책·카탈로그에서 Single-Agent와 네 proposal 병렬 구조를 비교하고 역할별 판단·Safety 의견 반영·요청 시간 보존을 검증함

## 4. 속성·불변식 테스트

- 사용자의 USER_OVERRIDE 없이 `requested_duration_minutes`가 바뀌지 않음
- 최종 루틴이 사용자의 requested duration을 보존함
- plan이 있는 최종 루틴의 `estimated_duration_seconds`가 `requested_duration_minutes * 60`과 정확히 일치함
- estimated duration과 actual elapsed time이 완료 상태에 영향을 주지 않음
- 운동 블록 완료 mutation의 중복 요청이 한 번만 반영됨
- 완료 취소는 세션 종료 전에만 PENDING으로 되돌릴 수 있음
- 다음 운동은 sequence상 첫 PENDING 블록임
- REST/STOP 응답에는 plan 없음
- 승인되지 않은 exercise/rule/alternative가 plan에 없음
- Training·Recovery·Safety·Feasibility 네 proposal이 final decision과 분리되고 Coordinator가 최종 루틴 한 개를 선택한다.
- 증상 사용자 시나리오에서 SafetyAgent의 `PASS`/`REVISE`/`BLOCKED` 의견은 Coordinator 결정에 반영하고, `NEEDS_INPUT`과 `FAILED`는 계획을 반환하지 않는 fail-closed 결과로 처리하며, 독립적인 최종 Safety 재검사는 실행하지 않는다.

안전 상태와 API 결과의 매핑은 다음과 같다.

| 상태 | API 결과 | 계획 |
|---|---|---|
| `NEEDS_INPUT` | `422 NEEDS_INPUT` | 반환하지 않음 |
| `FAILED` | `500/503 DECISION_FAILED` | 반환하지 않음 |
| `BLOCKED` | 정상 `DecisionResponse` | `REST` 또는 `STOP_AND_SEEK_HELP`, 계획 없음 |
| `PASS` | 정상 `DecisionResponse` | 운동 계획 반환 |
| `REVISE` | 정상 `DecisionResponse` | 조정된 운동 계획 반환 |

- Training은 목표·진행, Recovery는 회복·부하, Safety는 통증·제약, Feasibility는 시간·장소·장비·일정·선호를 추적하고, Coordinator는 네 결과와 최종 결정 이유를 추적한다.
- 동일한 입력·버전에서 Single-Agent 대비 네 proposal 병렬 구조의 역할 분리와 Safety 의견 반영 결과를 비교한다.
- 같은 입력 해시와 버전은 같은 후보와 action
- client가 rule version이나 agent weight를 지정할 수 없음
- 안전 상태가 PASS/REVISE가 아닌 최종 루틴은 반환·선택 불가
- `date_of_birth`가 유효한 `YYYY-MM-DD`이며 온보딩 필수이고, 만 나이는 사용자 로컬 날짜 기준으로 일시 계산되며 DB에 저장되지 않음
- 일반·민감·웨어러블·캘린더·마케팅 동의가 분리 저장됨
- agent proposal과 final decision이 분리되고 내부 추론이 노출되지 않음

## 5. 테스트 데이터

- 합성 UUID와 가상 프로필만 사용한다.
- 실제 이메일, 토큰, 이름, 건강 기록을 fixture에 넣지 않는다.
- raw reference data는 unit fixture로 직접 쓰지 않고 승인된 최소 normalized seed를 사용한다.
- 골든 결과는 policy/catalog/ruleset version과 함께 저장한다.

## 6. CI 게이트

구현 단계에서 다음 job을 독립 실행하도록 구성한다.

- docs/link/contract static checks
- backend format/lint/type/unit
- backend API/integration with PostgreSQL
- safety golden/fallback/reproducibility
- frontend format/lint/type/component/build
- migration up/down 또는 forward-fix validation

정확한 명령은 프로젝트 초기화 PR에서 확정한다. 실행하지 않은 테스트를 통과로 보고하지 않는다.

### Python 린터와 타입 체커

TASK-DATA-001의 Python 린터·포매터는 ruff, 타입 체커는 mypy로 선택했다. 설정과 고정
버전은 해당 코드와 함께 루트 `pyproject.toml`로 통합한다. `pyproject.toml`이 아직 없는
브랜치에서는 아래 명령을 계획된 게이트로만 취급하고 실행됐다고 보고하지 않는다. 초기 검사
범위는 `data/scripts`이며, backend 코드가 추가되면 같은 설정을 확장한다.

```powershell
python -m pip install --group dev  # Python 패키지 도구 확정 전 실행 예시
ruff check .
ruff format --check .
mypy
python -m unittest discover -s data/scripts/tests
```

Python 패키지 도구는 `TECHNICAL_PLAN.md`와 `LOCAL_DEVELOPMENT.md`의 미확정 항목을 따른다. `uv` 등으로 확정하면 설치 명령과 CI 명령을 같은 PR에서 갱신한다.

Pyright를 선택하지 않은 이유는 저장소의 Python 산출물이 표준 라이브러리 기반이고 CI에서
ruff와 동일한 Python 툴체인으로 실행하는 편이 단순하기 때문이다. 프론트엔드 타입 검사는
이 결정과 무관하다.

프론트 component 테스트는 최상단 count-up timer, 중앙 마스코트, 하단 순서형 운동 블록, 자세·설명 펼침, 체크·밀기 완료, 다음 블록 이동, 칼로리 추정치의 참고 문구, 캘린더 등록·수행 여부 확인·권한 거부, 웨어러블 수동 체크인 폴백을 검증한다. 타이머 값과 타이머 이벤트만 변경했을 때 블록과 세션 상태가 바뀌지 않는 음성 테스트를 포함한다. 수동 외부 기록은 MVP 테스트 대상에서 제외한다.

## 7. 대안과 선택 이유

E2E만으로 검증하지 않는다. 원인 파악이 느리고 안전 규칙의 모든 조합을 다루기 어렵다. snapshot만으로 agent 결과를 고정하지 않고 구조 필드와 도메인 불변식을 함께 검증한다.

## 8. 아직 확정되지 않은 사항과 질문

- React Native E2E 도구
- 성능 목표와 부하 테스트 임계값
- 외부 도메인 검수자가 승인할 골든 결과 형식
