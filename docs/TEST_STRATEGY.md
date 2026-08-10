# TEST_STRATEGY.md

## 1. 결정

테스트는 빠른 단위 테스트, 계약·DB 통합 테스트, 소수의 모바일 E2E, 안전 골든 시나리오로 구성한다. 안전 불변식과 결정 재현성은 일반 기능 테스트와 별도 suite로 고정한다.

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

1. 정상 상태는 원래 루틴 `KEEP`
2. 40분 상체·피로 MODERATE는 40분 요청과 CORE를 유지한 강도 `DOWNSHIFT`
3. 프로필 40분에서 사용자가 당일 30분으로 변경하면 30분을 사용하고 추가 축소하지 않음
4. 무릎 MILD/MODERATE는 검수 충돌 제외와 대체
5. 무릎 SEVERE는 계획 없는 `REST`
6. 중대한 이상 반응은 계획 없는 `STOP_AND_SEEK_HELP`
7. 웨어러블 없음은 수동 입력으로 정상 처리
8. LLM 실패는 동일 결정과 템플릿 설명
9. 안전 veto를 coordinator와 original 선택이 우회하지 못함
10. 필수 agent 하나 실패 시 decision `FAILED`, 계획 없음
11. 모든 운동 블록 체크는 경과 시간과 무관하게 `COMPLETED`
12. 일부 블록 체크는 경과 시간과 무관하게 `PARTIAL`
13. 완료 블록이 없으면 경과 시간이 길어도 `NOT_COMPLETED`
14. 닫힌 주 리포트 확인 전 다음 주 계획 확정 차단
15. 7일 또는 3회 미수행 복귀 모드
16. 계정 삭제 요청 즉시 접근 차단

## 4. 속성·불변식 테스트

- 사용자의 USER_OVERRIDE 없이 `requested_duration_minutes`가 바뀌지 않음
- primary와 lighter가 같은 requested duration을 사용함
- estimated duration과 actual elapsed time이 완료 상태에 영향을 주지 않음
- 운동 블록 완료 mutation의 중복 요청이 한 번만 반영됨
- 완료 취소는 세션 종료 전에만 PENDING으로 되돌릴 수 있음
- 다음 운동은 sequence상 첫 PENDING 블록임
- REST/STOP 응답에는 plan 없음
- 승인되지 않은 exercise/rule/alternative가 plan에 없음
- proposal은 정확히 4개이며 final decision과 분리
- 같은 입력 해시와 버전은 같은 후보와 action
- client가 rule version이나 agent weight를 지정할 수 없음
- 안전 상태가 PASS/REVISE가 아닌 plan은 선택 불가

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

Python 린터·포매터는 ruff, 타입 체커는 mypy로 확정했다. 설정과 고정 버전은 루트
`pyproject.toml`에 둔다. 현재 검사 범위는 `data/scripts`이며, backend 코드가 추가되면
같은 설정을 확장한다.

```powershell
pip install --group dev
ruff check .
ruff format --check .
mypy
python -m unittest discover -s data/scripts/tests
```

Pyright를 선택하지 않은 이유는 저장소의 Python 산출물이 표준 라이브러리 기반이고 CI에서
ruff와 동일한 Python 툴체인으로 실행하는 편이 단순하기 때문이다. 프론트엔드 타입 검사는
이 결정과 무관하다.

프론트 component 테스트는 최상단 count-up timer, 중앙 마스코트, 하단 순서형 운동 블록, 자세·설명 펼침, 체크·밀기 완료, 다음 블록 이동을 검증한다. 타이머 값만 변경했을 때 블록과 세션 상태가 바뀌지 않는 음성 테스트를 포함한다.

## 7. 대안과 선택 이유

E2E만으로 검증하지 않는다. 원인 파악이 느리고 안전 규칙의 모든 조합을 다루기 어렵다. snapshot만으로 agent 결과를 고정하지 않고 구조 필드와 도메인 불변식을 함께 검증한다.

## 8. 아직 확정되지 않은 사항과 질문

- React Native E2E 도구
- 성능 목표와 부하 테스트 임계값
- 외부 도메인 검수자가 승인할 골든 결과 형식
