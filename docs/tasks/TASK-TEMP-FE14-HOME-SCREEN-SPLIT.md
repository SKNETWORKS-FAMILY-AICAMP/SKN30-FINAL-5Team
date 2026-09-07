# TASK-TEMP-FE14-HOME-SCREEN-SPLIT: HomeScreen 책임 단위 분할

- 상태: DONE
- Primary owner: 프론트엔드 담당자
- Reviewers: 프론트엔드 또는 개발팀장 1명
- 관련 요구사항: `docs/tasks/2026-09-improvements/FRONTEND.md` FE-14
- 목표 브랜치: `refactor/temp-fe14-home-screen-split`

## 배경과 사용자 가치

`HomeScreen.tsx` 한 파일이 홈 상태 조합, 주간 현황, 루틴 카드, 체크인, 루틴 편집, 하단 탐색,
아이콘과 스타일을 모두 포함해 후속 FE-3·FE-4·FE-6·FE-10 작업의 충돌 위험이 크다. 기능과
화면 동작은 그대로 두고 책임별 모듈로 분리한다.

## 포함 범위

- 공개 `HomeScreen` API와 기존 re-export를 유지하는 진입점
- 홈 상태·이벤트 조합 컨테이너 분리
- 헤더와 주간 현황, 루틴 카드, 체크인 시트, 루틴 편집 시트, 하단 탐색 분리
- 아이콘·표현 헬퍼와 스타일 팩토리 분리
- 분할된 모든 파일을 1,000줄 미만으로 유지
- 소스 구조를 직접 확인하는 기존 테스트를 새 모듈 경계에 맞게 갱신

## 제외 범위

- 문구, 레이아웃, 색상, 애니메이션 또는 접근성 동작 변경
- 체크인·루틴 생성·운동 시작 규칙 변경
- API, DB, 응답 타입 또는 저장 payload 변경
- FE-3·FE-4·FE-6·FE-10의 기능 변경

## 인수 조건

1. 기존 화면 동작과 렌더 분기가 동일하다.
2. 새로 분리된 각 파일이 1,000줄 미만이다.
3. `HomeScreen`, `HomeBottomNavigation`, `bottomNavigationBottomPadding`, `HOME_LAYOUT`,
   `HOME_BACKGROUND_COLOR` 공개 경로가 유지된다.
4. 기존 홈 컴포넌트 테스트와 앱 통합 테스트가 통과한다.
5. 포맷, 린트, 타입 체크, 전체 테스트와 Android/iOS 프로덕션 export가 통과한다.

## 변경 예상 파일

- `frontend/src/features/home/HomeScreen.tsx`
- `frontend/src/features/home/HomeScreenContent.tsx`
- `frontend/src/features/home/HomeOverview.tsx`
- `frontend/src/features/home/HomeRoutineCard.tsx`
- `frontend/src/features/home/HomeChrome.tsx`
- `frontend/src/features/home/HomeCheckinSheet.tsx`
- `frontend/src/features/home/HomeEditRoutineSheet.tsx`
- `frontend/src/features/home/HomeSupport.tsx`
- `frontend/src/features/home/homeConstants.ts`
- `frontend/src/features/home/homeRevisionNotice.ts`
- `frontend/src/features/home/homeStyles.tsx`
- `frontend/src/features/home/homeSheetStyles.ts`
- `frontend/tests/HomeScreen.test.tsx`

## API·DB·호환성 영향

없음. 공개 컴포넌트 props와 re-export 경로를 유지하며 API·DB 계약을 수정하지 않는다.

## 안전·개인정보·보안 영향

안전 질문, 안전 중단 표시, 명시적 완료 기준과 payload를 변경하지 않는다. 개인정보 수집이나
로그도 추가하지 않는다.

## 테스트 계획

- `HomeScreen.test.tsx`, `PreviewGallery.test.tsx`, `App.test.tsx`
- 전체 Jest 테스트
- `npm.cmd run format:check`, `npm.cmd run lint`, `npm.cmd run typecheck`
- `npm.cmd run build:production`
- 분할 파일별 줄 수 검사

## 수동 확인

1. 체크인 전·체크인·생성 중·루틴 준비·조정·휴식 상태를 각각 연다.
2. 체크인 저장, 추천 이유, 운동 상세, 루틴 편집, 운동 시작을 확인한다.
3. 하단 탐색과 알림·프로필 진입이 기존과 동일한지 확인한다.

## 알려진 제한과 후속 작업

이 작업은 구조만 변경한다. 후속 기능은 해당 책임 파일에서 별도 이슈와 PR로 진행한다.

## 검증 결과

- 분할 파일 줄 수: 39~996줄, 모두 1,000줄 미만
- `npm.cmd run format:check`: 통과
- `npm.cmd run lint`: 통과
- `npm.cmd run typecheck`: 통과
- `npm.cmd test -- --runInBand tests/HomeScreen.test.tsx tests/PreviewGallery.test.tsx tests/App.test.tsx --silent`:
  3 suites, 121 tests 통과
- `npm.cmd test -- --runInBand --silent`: 32 suites, 547 tests 통과
- `npm.cmd run build:production`: Android와 iOS export 통과
