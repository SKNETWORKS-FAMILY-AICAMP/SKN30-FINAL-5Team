# 2026-09 프론트엔드 개선 통합 PR

- Owner: frontend
- 작업 지침: `docs/tasks/2026-09-improvements/FRONTEND.md`
- 통합 PR 브랜치: `feat/frontend-improvements-integrated-20260908`
- 원본 통합 스냅샷: `934a49ac1d8be3519153174bf87ff996af989feb`
- 최신화 기준: `origin/develop` = `3ba86e50f0c89af67b1ce100bf1062b53bbb7be4`
- 전략: 사용자 요청(2026-09-08)에 따라 #275 이후의 개별 PR #276~#291을 하나로 대체한다.
- 기존 개별 Draft와 브랜치·worktree는 검토 이력으로 보존한다. 병합 대상은 통합 PR이다.

## 범위

FE-1~13, FE-15와 오늘 계획 편집·홈 집계 API 연결을 포함한다.
FE-14(#275)는 이미 develop에 병합되었으며, 새 PR의 diff에는 후속 변경만 남긴다.
별도 UI 작업 브랜치 `feat/frontend-UI-0908`의 후속 디자인 변경은 포함하지 않는다.

1. 통합본의 별도 브랜치·worktree를 만들고 최신 develop을 merge한다.
2. FE-14 분할 커밋의 동일성을 확인하고 통합본의 후속 기능을 보존한다.
3. 장소 안내 배선과 체크인/프로필 테스트 정합성을 확인하고 회귀 테스트를 보완한다.
4. 최종 diff와 프론트 품질 검사를 확인하고 화면별 변경을 설명하는 PR을 생성한다.

## 통합 보완

- FE-14 원본 `c7eb275`와 병합된 `2dd1e08`의 tree diff가 비어 있음을 확인했다.
  add/add 충돌 6개는 통합본의 후속 FE 변경을 유지해 해결했다.
- `MainFlow`에서 `WorkoutScreen.exerciseGuideContext`로 실제 장소를 전달하고
  `ExerciseDetailSheet`까지 이어지는 배선을 보존했다.
- HOME/GYM에서 운동 이어하기 후 장소별 안내가 표시되고 반대 장소 안내는 숨겨지는
  통합 회귀 테스트를 `mainFlowRestore.test.tsx`에 추가했다.
- 삭제된 마이페이지 운동 시간 UI 테스트는 없고, 체크인 90분 선택 및 서버 거부 테스트는 유지한다.
- 집 데모는 서버 지갑을 사용한다. 보상·소비 API 성공 전에는 로컬 잔액을 근거로 성공 처리하지 않는다.

## 계약·보안·제한

- 백엔드·공개 API·DB 스키마 변경은 없다. 최신 develop의 백엔드 변경을 그대로 포함한다.
- 로그인 의존성 `expo-crypto`, `expo-web-browser`는 PKCE와 OS 인증 세션에 사용한다.
- 운영 OAuth callback/allowlist, 실제 기기 로그인, 프로필 이미지 저장은 실제 서버 확인이 필요하다.
- 끼끼패스는 비결제 목업이다. 전체 거래내역 API가 없어 현재 화면에서 확인된 수령 내역만 표시한다.
- 일부 기록·리포트에는 루틴 이름 필드가 없어 기존 표시명을 유지한다.
- 집의 배치·친밀도 등 서버 미지원 표현 상태는 로컬이다.
- 토큰·원시 건강 정보·provider secret을 새로 로그나 저장소에 추가하지 않는다.
- 자동 테스트 결과와 실제 서버 종단 검증 여부를 PR에서 구분한다.

## 검증 결과 (2026-09-08)

- Prettier 전체 검사, ESLint, TypeScript: 통과.
- 최종 전체 Jest: 36 suites / 603 tests 통과.
- HOME/GYM 장소 안내 회귀 테스트가 포함된 MainFlow 스위트: 13 tests 통과.
- Android/iOS production export: 통과. sandbox 밖에서 Hermes 실행을 허용해 검증했다.
- `git diff --check`: 통과. PR diff에 backend/API contract/DB schema 변경 없음.
- 로컬 검증은 기존 node_modules를 읽는 junction을 사용했다. GitHub CI는 lockfile로 새로 설치한다.
- 실제 서버·기기 종단 검증은 미실행이며 PR의 수동 확인 목록으로 남긴다.
