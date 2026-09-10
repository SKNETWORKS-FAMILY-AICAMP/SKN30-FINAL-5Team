# TASK-PROFILE-GOAL-ROUTINE-REFRESH: 프로필 운동 목표를 다음 루틴에 즉시 반영

- Primary owner: backend engineer
- Reviewers: frontend owner, development lead
- 목표 브랜치: `feat/profile-goal-live-routine`

## 배경과 사용자 가치

마이페이지에서 `primary_goal_code`를 변경해도 이전 목표로 만들어진 ACTIVE 루틴이 계속 조회되어,
홈의 자동 루틴 생성이 실행되지 않는다. 저장 직후 최신 프로필 목표가 다음 루틴 생성에 반영되어야 한다.

## 포함 범위

- 프로필 목표가 실제로 변경되면 새 목표와 불일치하는 ACTIVE 루틴을 같은 트랜잭션에서 ARCHIVED 처리
- 기존 운동 시간 변경에 따른 루틴 만료 동작 유지
- 홈의 기존 `ROUTINE_NOT_FOUND` 복구 흐름이 최신 프로필 목표로 루틴을 생성하는지 회귀 검증
- API 및 데이터 계약의 부수 효과 문서화

## 제외 범위

- 진행 중이거나 완료된 운동 세션 삭제·변경
- 과거 루틴 및 주간 계획 이력 삭제
- 목표 코드 목록, 운동 추천 알고리즘 또는 안전 규칙 변경

## 인수 조건

1. 마이페이지에서 운동 목표를 변경하면 이전 목표의 ACTIVE 루틴은 더 이상 현재 루틴으로 조회되지 않는다.
2. 다음 홈 조회는 최신 프로필 목표를 사용해 새 루틴을 생성한다.
3. 같은 목표를 다시 저장하거나 목표 외 필드만 수정하면 목표 때문에 루틴이 만료되지 않는다.
4. 프로필 수정과 루틴 만료는 하나의 DB 트랜잭션으로 처리된다.
5. 공개 API 필드와 DB 스키마는 변경하지 않는다.

## 변경 예상 파일

- `backend/app/modules/profiles/ports.py`
- `backend/app/modules/profiles/service.py`
- `backend/app/db/repositories/routine.py`
- `backend/tests/api/test_profile_settings.py`
- `backend/tests/integration/test_routine_repository.py`
- `backend/tests/unit/test_current_routine_query.py`
- `frontend/tests/demoFlow.test.tsx`
- `docs/API_CONTRACT.md`
- `docs/DATA_MODEL.md`
- `docs/DOMAIN_RULES.md`

## 위험 및 호환성

- API: 필드 변경 없음. 프로필 목표 변경 시 현재 루틴 조회 결과가 404로 바뀌는 의도된 동작 변화가 있다.
- DB: 마이그레이션 없음. 기존 `routines.status_code`만 갱신한다.
- 안전·개인정보: 안전 판단과 건강정보 처리를 변경하지 않으며 새 데이터 수집이나 로그를 추가하지 않는다.
- 호환성: 기존 프론트엔드의 404 자동 복구 및 최신 프로필 재조회 흐름을 재사용한다.

## 테스트 계획

- 프로필 API 단위 테스트: 목표 변경, 목표 외 변경, 시간·목표 동시 변경
- 저장소 통합 테스트: 다른 목표 ACTIVE 루틴만 ARCHIVED 처리, 동일 목표·다른 사용자·과거 루틴 보존
- 기존 프로필/루틴 API 및 프론트엔드 홈·마이페이지 회귀 테스트

## 수동 확인

마이페이지에서 운동 목표를 변경한 뒤 홈으로 이동해 새 루틴의 `goal_code`와 운동 구성이 변경한 목표와
일치하는지 확인한다.
