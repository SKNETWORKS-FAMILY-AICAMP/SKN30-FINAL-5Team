# TASK-TEMP-FE12: 바나나코인·끼끼패스 화면

## 목표

- 서버 `GET /api/v1/rewards`의 잔액과 일일 보상 상태를 사용자에게 보여준다.
- 일일 보상은 `POST /api/v1/rewards/daily-reward/claim`으로만 수령한다.
- 끼끼패스는 결제를 시도하지 않는 목업으로만 표시한다.

## 구현 계획

1. rewards 응답과 mutation 계약을 프론트엔드 타입과 API client에 추가한다.
2. 지갑 잔액·일일 보상·로딩·오류·빈 상태를 표시하는 화면을 추가한다.
3. 끼끼패스 탭에 목업·미확정·비결제 상태를 명시한다.
4. 끼끼의 집 바나나 칩에서 해당 화면으로 진입하는 경로와 컴포넌트·API 테스트를 추가한다.
5. 집의 잔액·먹이·아이템 구매를 서버 지갑과 `POST /api/v1/rewards/spend`에 연결한다.
6. `CLAIM_DAILY_REWARD` 알림을 지갑 화면으로 연결한다.

## 예상 변경 파일

- `frontend/src/api/endpoints.ts`
- `frontend/src/api/types.ts`
- `frontend/src/features/rewards/RewardsScreen.tsx`
- `frontend/src/features/house/MascotHouseContent.tsx`
- `frontend/src/features/house/MascotHouseScreen.tsx`
- `frontend/src/features/home/NotificationSheet.tsx`
- `frontend/src/app/MainFlow.tsx`
- `frontend/tests/RewardsScreen.test.tsx`
- `frontend/tests/MascotHouseScreen.test.tsx`
- `frontend/tests/apiEndpoints.test.ts`

## 제약과 위험

- 현재 공개 API에는 거래 내역 목록을 조회하는 endpoint가 없다. 가짜 내역을 만들지 않고, 현재 화면에서 서버가 직접 반환한 claim transaction만 `이번 화면에서 확인된 내역`으로 표시한다. 전체 내역은 조회 API 계약이 추가될 때까지 blocker다.
- 잔액과 소비 성공 여부는 서버 지갑이 기준이다. 먹이와 아이템 구매는 서버 성공 뒤에만 로컬 집 상태를 반영하며, 서버가 거절하면 로컬 상태를 바꾸지 않는다.
- `HouseStore`는 배치·친밀도 같은 서버 미지원 집 표현 상태만 유지한다. 저장된 로컬 바나나 값은 화면의 잔액 근거로 사용하지 않는다.
- 끼끼패스는 백엔드·DB·결제 계약이 없다. 구독 상태를 저장하거나 결제 정보를 받지 않는다.
- FE-9도 `MascotHouseContent.tsx`를 변경하므로 나중에 한 번의 수동 rebase가 필요하다. FE-12는 바나나 칩의 `+` 진입점만 변경한다.
- 공개 API·DB 스키마·건강 데이터·인증 처리는 변경하지 않는다.

## 검증

- 변경 파일 Prettier
- ESLint
- TypeScript typecheck
- `RewardsScreen`, `MascotHouseScreen`, API endpoint 컴포넌트/계약 테스트
- 전체 프론트엔드 테스트
- Android·iOS production build
