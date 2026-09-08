# TASK-TEMP-FE13-WEARABLE-UI-REMOVAL: 웨어러블 사용자 UI 제거

- 상태: DONE
- Primary owner: 프론트엔드 담당자
- Reviewers: 프론트엔드 또는 개발팀장 1명
- 관련 요구사항: `docs/tasks/2026-09-improvements/FRONTEND.md` FE-13
- 관련 결정: G2
- 목표 브랜치: `feat/temp-fe13-remove-wearable-ui`
- 선행 커밋: FE-8 `fdd6fa2`

## 배경과 사용자 가치

G2는 현재 서비스에서 웨어러블 관련 표기를 사용자에게 전부 숨기되, 미래 확장성과 기존 데이터
호환성을 위한 값 도메인은 유지하도록 확정했다. 온보딩과 마이페이지에서 제공하지 않는 연동
기능을 약속하는 표현을 제거한다.

## 포함 범위

- 온보딩 선택 동의에서 웨어러블 연동 항목 제거
- 마이페이지의 연동 기기 행과 웨어러블 연동 동의 항목 제거
- 레거시 계정 화면의 웨어러블 연동 동의 항목 제거
- 기기 연동을 언급하는 준비 중 안내 문구 정리
- 마케팅 동의 변경 시 기존 웨어러블 동의 값을 노출 없이 보존

## 제외 범위

- `sleep_source_code`의 `MANUAL | WEARABLE` 값 도메인 변경
- 기존 웨어러블 동의 기록 삭제
- 백엔드 동의 목록 및 데이터 모델 변경(BL-3)

## 인수 조건

1. 온보딩에 웨어러블 동의 항목이 없다.
2. 마이페이지와 계정 화면에 연동 기기·웨어러블 연동 항목이 없다.
3. 온보딩 요청은 비노출 필드를 `false`로 보내 현재 계약과 호환된다.
4. 다른 선택 동의 변경 시 저장된 웨어러블 동의 값이 임의로 바뀌지 않는다.
5. `sleep_source_code?: 'MANUAL' | 'WEARABLE' | null` 타입이 유지된다.
6. 수면 시간 수동 입력과 기존 체크인 요청이 그대로 동작한다.
7. 포맷, 린트, 타입 체크, 관련 테스트와 프로덕션 빌드가 통과한다.

## 변경 예상 파일

- `frontend/src/features/onboarding/OnboardingScreen.tsx`
- `frontend/src/features/home/homeSecondaryModel.ts`
- `frontend/src/features/home/MyPageScreen.tsx`
- `frontend/src/features/profile/AccountScreen.tsx`
- `frontend/tests/demoFlow.test.tsx`
- `frontend/tests/MyPageContainer.test.tsx`
- `frontend/tests/GapClosureScreens.test.tsx`
- `frontend/tests/HomeSecondaryScreens.test.tsx`

## API·DB 영향

공개 API와 DB 변경은 없다. 온보딩 요청의 필수 consent shape를 유지하기 위해
`wearable_integration: false`를 보낸다. 마이페이지 동의 저장은 서버에서 읽은 비노출 값을 함께
보존한다.

## 안전·개인정보·보안 영향

현재 제공하지 않는 건강 데이터 연동 안내와 선택 경로를 제거한다. 수동 체크인은 유지하고,
식별자·건강·웨어러블 원본 데이터를 새로 수집하거나 로그에 기록하지 않는다.

## 테스트 계획

- 온보딩 체크박스가 4개이며 웨어러블 항목이 없는지 확인
- 온보딩 완료 payload에서 웨어러블 동의가 `false`인지 확인
- 마이페이지·계정 화면에 웨어러블 관련 항목이 없는지 확인
- 마케팅 동의 변경 payload가 비노출 값을 보존하는지 확인
- 수동 수면 입력의 `sleep_source_code: MANUAL` 회귀 확인
- 포맷, 린트, 타입 체크, 전체 Jest, Android/iOS 프로덕션 export

## 수동 확인

1. 온보딩 마지막 동의 단계에서 마케팅 선택지만 보이는지 확인한다.
2. 마이페이지에서 연동 기기 행과 웨어러블 동의 항목이 없는지 확인한다.
3. 수동 수면 시간을 입력해 체크인을 완료한다.
4. 마케팅 동의를 변경하고 기존 웨어러블 동의 기록이 보존되는지 네트워크 요청으로 확인한다.

## 알려진 제한과 후속 작업

백엔드가 반환하는 동의 목록과 기존 기록은 BL-3에서 별도로 정리한다. 타입 도메인은 의도적으로
유지한다.

## 검증 결과

- `npm.cmd run format:check`: 통과
- `npm.cmd run lint`: 통과
- `npm.cmd run typecheck`: 통과
- `npm.cmd test -- --runInBand tests/demoFlow.test.tsx tests/MyPageContainer.test.tsx tests/GapClosureScreens.test.tsx tests/HomeSecondaryScreens.test.tsx --silent`:
  4 suites, 143 tests 통과
- `npm.cmd test -- --runInBand --silent`: 32 suites, 546 tests 통과
- `npm.cmd run build:production`: Android와 iOS export 통과
