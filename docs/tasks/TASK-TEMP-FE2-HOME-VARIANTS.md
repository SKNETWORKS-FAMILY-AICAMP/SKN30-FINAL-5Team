# TASK-TEMP-FE2-HOME-VARIANTS: 집 운동 변형 운동 노출 제한

- 상태: DONE
- Primary owner: 프론트엔드
- 관련 요구사항: `docs/tasks/2026-09-improvements/FRONTEND.md` FE-2
- 의존 작업: BM-3 변형 운동 조회 계약, FE-14 HomeScreen 책임 분할
- 목표 브랜치: `fix/temp-fe2-home-variants`

## 범위

- `location_code`가 `HOME`인 홈 루틴과 운동 진행 화면에서만 검토된 변형 운동 진입점을 노출한다.
- `GYM`과 `OUTDOOR`에서는 변형 운동 조회를 보내지 않고 진입점을 숨긴다.
- `HOME` 조회가 빈 목록을 반환하면 문맥상 미지원 상태와 구분해 조회는 완료하되 진입점을 숨긴다.
- `HOME` 조회 실패 시 기존 재시도 상태를 유지한다.
- 백엔드 의사결정 로직, 운동 세션 기록, DB 스키마는 변경하지 않는다.

## 예상 변경 파일

- `frontend/src/api/endpoints.ts`
- `frontend/src/app/MainFlow.tsx`
- `frontend/src/features/home/HomeContainer.tsx`
- `frontend/src/features/home/HomeScreenContent.tsx`
- `frontend/src/features/home/HomeRoutineCard.tsx`
- `frontend/src/features/workout/ExerciseVariants.tsx`
- `frontend/src/features/workout/WorkoutScreen.tsx`
- `frontend/tests/apiEndpoints.test.ts`
- `frontend/tests/HomeScreen.test.tsx`
- `frontend/tests/WorkoutScreen.test.tsx`
- `frontend/tests/demoFlow.test.tsx`

## API와 호환성 위험

- BM-3의 `GET /api/v1/exercises/{exercise_id}/variants?location_code=...` 계약을 사용한다.
- `location_code`를 모르는 기존 호출은 쿼리를 생략해 기존 HOME 호환 동작을 보존한다.
- `items: []`는 오류가 아니며, 클라이언트가 임의 변형 운동이나 대체 문구를 만들지 않는다.
- 공개 응답 필드, 요청 본문, DB 스키마 변경은 없다.

## 검증 계획

- API endpoint 쿼리 직렬화 테스트
- Home/Workout의 HOME 목록, HOME 빈 목록, GYM/OUTDOOR 억제, 오류 재시도 테스트
- 세션 시작·재개 시 위치 문맥 전달 테스트
- `HomeScreen.test.tsx` 전체 회귀 테스트
- formatter, linter, type checker, production build

## 보안과 개인정보 영향

위치 문맥은 기존의 안정된 `location_code`만 사용한다. GPS, 자유 텍스트, 건강 원본 데이터나 식별자를 추가로 수집하거나 기록하지 않는다.

## 수동 확인

1. 집 체크인 후 장비 변형이 있는 운동에 장비 버튼이 표시되는지 확인한다.
2. 집 체크인에서 빈 변형 목록인 운동은 장비 버튼이 사라지는지 확인한다.
3. 헬스장과 야외 체크인에서는 장비 변형 버튼이 없고 조회 요청도 발생하지 않는지 확인한다.
4. 집 운동 중 조회 실패 시 재시도 버튼이 표시되고 재시도가 가능한지 확인한다.

## 검증 결과

- FE-2 관련 4 suites: 4 suites, 11 tests 통과
- `HomeScreen.test.tsx`: 1 suite, 59 tests 통과
- `npm.cmd run format:check`: 통과
- `npm.cmd run lint`: 통과
- `npm.cmd run typecheck`: 통과
- Android/iOS production export: 통과
