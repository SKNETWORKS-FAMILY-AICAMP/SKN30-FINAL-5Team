# TASK-TEMP-FE8-COACHING-STYLE-CLEANUP: 코칭 스타일 선택 UI 제거

- 상태: DONE
- Primary owner: 프론트엔드 담당자
- Reviewers: 프론트엔드 또는 개발팀장 1명
- 관련 요구사항: `docs/tasks/2026-09-improvements/FRONTEND.md` FE-8
- 관련 결정: G6
- 목표 브랜치: `feat/temp-fe8-coaching-style-cleanup`

## 배경과 사용자 가치

G6는 모든 사용자에게 동일한 기본 코칭 컨텍스트를 적용하고 코칭 스타일 선택 화면을 노출하지
않도록 확정했다. 온보딩 단계를 줄이면서도 완료 흐름, 진행 표시, 서버 오류 복귀가 실제 단계
구성과 일치해야 한다.

## 포함 범위

- 온보딩 단계 목록, 상태, 렌더 분기와 완료 판정에서 코칭 스타일 제거
- 온보딩 요청 본문에서 `coaching_style_code` 제거
- 서버 검증 오류의 단계 매핑에서 제거된 필드 정리
- 마이페이지의 코칭 스타일 표시·수정 UI와 저장 동작 제거
- 실제 8단계 진행 표시와 전체 완료 흐름 검증

## 제외 범위

- 백엔드 기본 코칭 스타일과 설명 템플릿 변경(BL-1)
- 응답의 legacy `coaching_style_code` 제거 및 DB 컬럼 마이그레이션(BL-1 2단계)
- 프로필 설정 API가 기존 필드를 수용하는 호환성 제거

## 인수 조건

1. 온보딩에 코칭 스타일 선택 화면이 없다.
2. 온보딩이 처음부터 끝까지 완료된다.
3. 진행 표시가 실제 8단계와 일치한다.
4. 제거된 필드가 서버 오류 단계 매핑에 남지 않는다.
5. 마이페이지에 코칭 스타일 표시와 수정 항목이 없다.
6. 온보딩 요청 본문에 `coaching_style_code`가 포함되지 않는다.
7. 포맷, 린트, 타입 체크, 관련 테스트와 프로덕션 빌드가 통과한다.

## 변경 예상 파일

- `frontend/src/api/types.ts`
- `frontend/src/features/onboarding/OnboardingScreen.tsx`
- `frontend/src/features/home/MyPageContainer.tsx`
- `frontend/src/features/home/MyPageScreen.tsx`
- `frontend/tests/demoFlow.test.tsx`
- `frontend/tests/MyPageContainer.test.tsx`
- `frontend/tests/PreviewGallery.test.tsx`

## API 영향

프론트의 `OnboardingRequest`에서 선택 필드를 제거한다. 서버는 필드가 없을 때 `SUPPORTIVE`
기본값을 적용하므로 기존 배포와 호환된다. `MeProfile`, `OnboardingResponse`, 프로필 설정 요청의
legacy 필드는 BL-1 2단계까지 유지한다.

## DB·마이그레이션 영향

없음. DB 제약과 컬럼 제거는 BL-1의 단계별 배포 범위다.

## 안전·개인정보·보안 영향

건강·안전 입력과 판정은 변경하지 않는다. 사용자가 선택하지 않는 선호 필드를 새 요청에서
제외하며, 식별자나 건강 정보를 로그에 추가하지 않는다.

## 테스트 계획

- 단계 배열에 `coachingStyle`이 없고 길이가 8인지 확인
- 온보딩 전체 완료와 요청 payload의 필드 부재 확인
- 마이페이지 코칭 스타일 라벨과 선택지 부재 확인
- 서버 검증 오류의 단계 복귀 회귀 테스트
- 포맷, 린트, 타입 체크, 전체 Jest, Android/iOS 프로덕션 export

## 수동 확인

1. 신규 사용자로 온보딩을 열고 1/8부터 마지막 단계까지 진행한다.
2. 코칭 스타일 화면 없이 동의 후 온보딩이 완료되는지 확인한다.
3. 마이페이지에서 코칭 스타일 카드와 선택지가 없는지 확인한다.
4. 네트워크 요청 본문에 `coaching_style_code`가 없는지 확인한다.

## 알려진 제한과 후속 작업

응답 타입과 서버·DB의 legacy 필드는 BL-1 2단계 안정화 이후 제거한다.

## 검증 결과

- `npm.cmd run format:check`: 통과
- `npm.cmd run lint`: 통과
- `npm.cmd run typecheck`: 통과
- `npm.cmd test -- --runInBand tests/demoFlow.test.tsx tests/MyPageContainer.test.tsx --silent`:
  2 suites, 108 tests 통과
- `npm.cmd test -- --runInBand tests/PreviewGallery.test.tsx --silent`: 37 tests 통과
- `npm.cmd test -- --runInBand --silent`: 32 suites, 546 tests 통과
- `npm.cmd run build:production`: Android와 iOS export 통과

첫 전체 테스트에서 프리뷰의 기존 9단계 기대값 두 곳이 실패해 실제 8단계로 수정했다. 수정 후
프리뷰 스위트와 전체 스위트를 다시 실행해 통과를 확인했다. 중간에 프리뷰의 비관련 Workout
비동기 대기 테스트가 한 차례 시간 초과됐으나 해당 테스트 단독, 프리뷰 전체, 전체 스위트
재실행에서는 재현되지 않았다.
