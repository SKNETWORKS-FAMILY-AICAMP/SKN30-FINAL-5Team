# TASK-TEMP-DECISION-PLAN-EDIT-API: 오늘 계획 편집 API 연결

- Primary owner: frontend engineer
- Reviewers: frontend owner, backend owner
- 관련 요구사항: ADR-0018 D4/D5, `docs/API_CONTRACT.md` 10.7
- 관련 ADR: ADR-0018
- 목표 브랜치: `fix/temp-decision-plan-edit-api`

## 배경과 사용자 가치

오늘 계획의 세트·횟수와 순서 편집 UI는 현재 존재하지 않는 통합 저장 API를 선택적으로 호출하고,
그 API가 없으면 변경을 앱 메모리에만 남긴다. 최신 백엔드가 제공하는 revision 기반 항목 수정 및
순서 변경 API를 연결해 사용자가 본 결과와 서버에 저장된 최종 계획을 일치시킨다.

## 포함 범위

- `WorkoutPlan.plan_revision`과 계획 편집 요청·응답 타입 추가
- 계획 항목 세트·횟수 PATCH 및 순서 PUT API 클라이언트 구현
- Home 편집 흐름에서 실제 API를 필수 호출하고 서버 `final_plan`을 반영
- 완료한 운동 블록을 제외한 순서 payload 구성
- stale conflict, 일반 오류, 동일 idempotency key 재시도 처리
- API·계획 유틸·Home 컴포넌트 테스트 보완

## 제외 범위

- 백엔드 코드, DB 스키마, API 계약 변경
- `GET /api/v1/home` 전환
- 운동 종류·장소·안전 판단을 바꾸는 클라이언트 로직
- 주간 계획 revision 복원 API

## 인수 조건

1. 항목 수정 요청은 `expected_plan_id`, `expected_plan_revision`, `sets`, `reps`와 UUID
   `Idempotency-Key`를 전송한다.
2. 순서 변경 요청은 `expected_plan_id`, `expected_plan_revision`, 서버가 이동을 허용하는 전체 항목
   ID 순서를 전송하며, 진행 중 세션에서는 완료 항목을 제외한다.
3. 성공 시 응답의 `final_plan`과 `plan_revision`이 Home의 단일 계획 상태가 된다.
4. 로컬 전용 저장 경로와 미구현 optional API capability가 제거된다.
5. 모호한 전송 실패는 같은 idempotency key로 재시도할 수 있고, stale/거부 응답은 저장된 결정을
   다시 읽어 로컬 낙관 상태를 제거한다.
6. formatter, linter, type checker, 관련 컴포넌트·API 테스트, production build가 통과한다.

## 변경 예상 파일

- `frontend/src/api/types.ts`
- `frontend/src/api/endpoints.ts`
- `frontend/src/api/workoutPlan.ts`
- `frontend/src/features/home/HomeContainer.tsx`
- `frontend/src/features/home/HomeScreen.tsx`
- `frontend/tests/apiEndpoints.test.ts`
- `frontend/tests/workoutPlan.test.ts`
- `frontend/tests/demoFlow.test.tsx`
- 이 작업 문서

## API 영향

공개 계약은 변경하지 않는다. 이미 문서화된 두 `/api/v1/decisions/{decision_id}` 하위 mutation을
프런트 typed client에 추가한다. 각 요청은 revision 낙관 잠금과 idempotency key를 사용한다.

## DB·마이그레이션 영향

없음.

## 안전·개인정보·보안 영향

서버 최종 계획만 확정 상태로 사용하고 클라이언트는 안전·운동 처방 판단을 추가하지 않는다.
인증 토큰, 사용자 식별자, 건강 기록을 새로 저장하거나 로그에 남기지 않는다.

## 선행 관계와 차단 요소

백엔드 계획 편집 API와 `plan_revision` 계약이 `origin/develop` 905d263에 반영되어 있다.

## 테스트 계획

- API endpoint method/path/body/idempotency header 테스트
- revision 및 완료 항목 제외 순서 request 유틸 테스트
- Home 성공, stale rollback/recovery, 모호한 실패 동일 키 재시도 테스트
- frontend format check, lint, typecheck, production build

### 실행 결과 (2026-09-07)

- `npm.cmd run typecheck`: 통과
- `npm.cmd run lint`: 통과
- `npm.cmd run format:check`: 통과
- `npm.cmd test -- --runInBand tests/apiEndpoints.test.ts tests/workoutPlan.test.ts tests/demoFlow.test.tsx`:
  3 suites, 97 tests 통과
- production export: 공용 의존성의 `.bin/expo.cmd`가 없어 스크립트 wrapper는 실행되지 않았다. 동일한
  로컬 Expo CLI로 Android export를 시작했으나 다른 병렬 작업과의 환경 경합 중 Node가 약 189MB
  heap에서 `Zone Allocation failed - process out of memory`로 종료됐다. 루트 통합 단계에서 Android와
  iOS export를 순차 재검증한다.

## 수동 확인

1. Home에서 세트·횟수를 저장하고 서버가 반환한 값과 revision이 표시되는지 확인한다.
2. 계획 순서를 바꾸고 재진입 후 서버 순서가 유지되는지 확인한다.
3. 409 stale 및 네트워크 실패를 주입해 복구·재시도 상태를 확인한다.

## 알려진 제한과 후속 작업

Home 초기 데이터 집계를 `GET /api/v1/home`으로 전환하는 작업은 별도 이슈다.
이 worktree의 production export는 위 환경 메모리 부족으로 완료되지 않았으므로 통합 검증이 필요하다.
