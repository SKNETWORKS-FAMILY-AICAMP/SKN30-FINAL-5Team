# TASK-TEMP-FE10-ROUTINE-NAME: 서버 루틴 이름 표시

- 상태: DONE
- Primary owner: 프론트엔드 담당자
- Reviewers: 프론트엔드 또는 개발팀장 1명
- 관련 요구사항: `docs/tasks/2026-09-improvements/FRONTEND.md` FE-10
- 목표 브랜치: `feat/temp-fe10-routine-name-after-fe14`
- 선행 브랜치: `refactor/temp-fe14-home-screen-split`
- 백엔드 선행: BM-5 (`origin/develop` 반영 확인)

## 배경과 목표

프론트가 운동 유형과 부위 코드를 조합해 이름을 결정하면 서버가 같은 루틴에 부여한 이름과
화면별 표시가 달라질 수 있다. BM-5가 제공하는 `routine_name`을 우선 표시하고, 과거 응답에는
기존 표시명 계산을 호환 폴백으로 사용한다.

## 구현 계획

1. `RoutineDay`와 `WorkoutPlan`에 BM-5의 선택적 이름·근거·규칙 버전 필드를 반영한다.
2. 서버 이름 우선·구버전 폴백 규칙을 공용 workout-plan 유틸리티 한 곳에 둔다.
3. 오늘 루틴 카드, 운동 실행 화면, 기본 루틴 요약이 같은 공용 규칙을 사용하게 한다.
4. 서버 이름과 이름이 없는 구버전 응답을 컴포넌트·유닛 테스트로 검증한다.

## 변경 예상 파일

- `frontend/src/api/types.ts`
- `frontend/src/api/workoutPlan.ts`
- `frontend/src/features/home/HomeScreenContent.tsx`
- `frontend/src/features/home/homeModel.ts`
- `frontend/src/features/home/MapHomeScreen.tsx`
- `frontend/src/features/workout/WorkoutScreen.tsx`
- `frontend/tests/workoutPlan.test.ts`
- `frontend/tests/WorkoutScreen.test.tsx`
- `frontend/tests/HomeSecondaryScreens.test.tsx`

## API·DB 영향

프론트 타입에 백엔드가 이미 제공하는 선택적 필드를 추가한다. 요청, 데이터베이스, 공개 API는
변경하지 않는다. 선택적으로 두어 이전 서버와 저장된 응답을 계속 읽을 수 있다.

## 안전·개인정보·보안 영향

서버가 결정한 사용자 표시명만 읽으며 새로운 건강·식별 정보를 수집하거나 기록하지 않는다.
루틴 구성과 안전 판단 로직은 변경하지 않는다.

## 알려진 제한

현재 운동 세션 목록·상세와 주간 리포트 응답에는 `routine_name`이 없다. 따라서 해당 응답만
가진 과거 운동 기록과 주간 리포트에 같은 이름을 새로 표시할 수 없다. 프론트에서 이름을
재계산하거나 추정하지 않으며, 계약에 필드가 추가되면 동일 공용 유틸리티를 연결한다.

## 검증 계획

- 서버 이름 우선 및 구버전 폴백 유닛 테스트
- 운동 실행 화면의 서버 이름 표시 컴포넌트 테스트
- Home/Workout 관련 회귀 테스트
- 포맷, 린트, 타입 체크, 전체 테스트, Android/iOS 프로덕션 export

## 수동 확인

1. `routine_name`이 있는 최종 추천을 열어 홈 카드와 운동 실행 헤더가 같은 이름인지 확인한다.
2. `routine_name`이 없는 preview/과거 응답에서 기존 코드 기반 이름이 보이는지 확인한다.
3. 기본 루틴 요약에서 서버가 제공한 이름이 우선 표시되는지 확인한다.

## 검증 결과

- `npm.cmd run format:check`: 통과
- `npm.cmd run lint`: 통과
- `npm.cmd run typecheck`: 통과
- 서버 이름·구버전 폴백 유닛 테스트: 12 tests 통과
- 서버 이름 운동 화면 테스트: 1 test 통과
- Home/Map 관련 테스트: 78 tests 통과
- `npm.cmd test -- --runInBand --silent`: 32 suites, 551 tests 통과
- `npm.cmd run build:production`: Android와 iOS export 통과

병렬 실행 중 기존 Workout 테스트가 한 차례 타이밍 실패했지만, 전체 스위트를 단독 재실행해
모든 테스트가 통과하는 것을 확인했다.
