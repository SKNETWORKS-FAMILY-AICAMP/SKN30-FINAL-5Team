# TASK-TEMP-FE5-PROFILE-CLEANUP: 마이페이지 legacy 프로필 입력 제거

- 상태: DONE
- Primary owner: 프론트엔드 담당자
- Reviewers: 프론트엔드 또는 개발팀장 1명
- 관련 요구사항: `docs/tasks/2026-09-improvements/FRONTEND.md` FE-5
- 관련 ADR: ADR-0017
- 목표 브랜치: `feat/temp-fe5-profile-cleanup`

## 배경과 사용자 가치

ADR-0017에서 수집 대상에서 제외한 성별, 키, 기본 운동 장소와 기본 운동 시간이 마이페이지에
남아 있다. 사용자가 수정할 수 없는 legacy 정보를 계속 노출하지 않고, 현재 계약에서 필요한
체중과 생년월일만 유지한다.

## 포함 범위

- 기본 프로필 편집기에서 성별과 키 입력 제거
- 내 운동 정보에서 운동 장소와 기본 운동 시간 요약·수정 제거
- 개인정보 안내 문구를 남은 민감 입력과 일치하도록 수정
- 제거한 필드가 프로필 수정 요청에 포함되지 않는지 테스트

## 제외 범위

- 백엔드 응답 필드와 DB 컬럼 제거
- 체중과 생년월일 제거
- 프로필 사진 저장 문제 수정
- 코칭 스타일과 웨어러블 UI 제거

## 인수 조건

1. 프로필 수정 화면에 성별과 키 입력이 없다.
2. 체중과 생년월일 입력은 유지된다.
3. 마이페이지 요약과 편집 진입점에 운동 장소와 기본 운동 시간이 없다.
4. 개인정보 안내 문구가 생년월일과 체중만 설명한다.
5. 프로필 저장 요청에 성별, 키, 장소, 기본 운동 시간이 포함되지 않는다.
6. 포맷, 린트, 타입 체크, 관련 컴포넌트 테스트와 프로덕션 빌드가 통과한다.

## 변경 예상 파일

- `frontend/src/features/home/MyPageProfileEditor.tsx`
- `frontend/src/features/home/myPageModel.ts`
- `frontend/src/features/home/homeSecondaryModel.ts`
- `frontend/tests/MyPageContainer.test.tsx`

## API 영향

없음. legacy 응답 타입과 공개 필드는 유지한다.

## DB·마이그레이션 영향

없음. 컬럼 제거는 BL-7 2단계 후속 작업이다.

## 안전·개인정보·보안 영향

불필요한 성별·키·장소 노출과 재수집 경로를 줄인다. 체중과 생년월일은 기존 개인정보 처리
경계를 유지하고 로그에 기록하지 않는다.

## 선행 관계와 차단 요소

BL-7의 공개 응답 필드 유지 단계와 호환된다. 컬럼 제거 완료를 기다릴 필요는 없다.

## 테스트 계획

- 마이페이지 요약·편집 진입점에서 제거 항목이 보이지 않는지 확인
- 기본 프로필 편집에서 성별·키가 없고 체중·생년월일이 남는지 확인
- 저장 요청 payload에 제거 필드가 포함되지 않는지 확인
- `npm.cmd run format:check`, `npm.cmd run lint`, `npm.cmd run typecheck`
- 관련 Jest 테스트 및 `npm.cmd run build:production`

## 수동 확인

1. 마이페이지의 프로필 수정과 내 운동 정보를 연다.
2. 성별·키·운동 장소·기본 운동 시간 항목이 없는지 확인한다.
3. 생년월일 또는 체중을 변경해 정상 저장되는지 확인한다.

## 알려진 제한과 후속 작업

legacy API 응답 필드와 DB 컬럼은 BL-7 2단계까지 남는다.

## 검증 결과

- `npm.cmd run format:check`: 통과
- `npm.cmd run lint`: 통과
- `npm.cmd run typecheck`: 통과
- `npm.cmd test -- --runInBand tests/MyPageContainer.test.tsx tests/HomeSecondaryScreens.test.tsx`:
  2 suites, 48 tests 통과
- `npm.cmd test -- --runInBand --silent`: 32 suites, 546 tests 통과
- `npm.cmd run build:production`: Android와 iOS export 통과

샌드박스 안의 첫 빌드는 Hermes 하위 프로세스 실행 제한으로 `spawn EPERM`이 발생했으며,
같은 명령을 승인된 권한으로 재실행해 두 플랫폼의 번들을 확인했다. 관련 테스트가 출력하는
기존 React `act(...)` 경고는 별도 테스트 안정화 과제로 남긴다.
