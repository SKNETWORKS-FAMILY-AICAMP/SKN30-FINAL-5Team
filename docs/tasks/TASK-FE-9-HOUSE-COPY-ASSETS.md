# TASK-FE-9: 끼끼의 집 버튼 에셋과 교감 문구 정리

- Primary owner: 프론트엔드
- Reviewers: 프론트엔드 또는 개발팀장 1명
- 관련 요구사항: `docs/tasks/2026-09-improvements/FRONTEND.md` FE-9
- 관련 ADR: 없음
- 목표 브랜치: `feat/fe-9-house-copy-assets`

## 배경과 사용자 가치

끼끼의 집에서 집 꾸미기 진입점의 임시 도형 아이콘을 사용자 제공 이미지로 교체하고,
쓰다듬기와 교감하기가 섞여 있던 사용자 문구와 접근성 라벨을 하나의 확정 초안으로 맞춘다.

## 포함 범위

- 사용자 제공 `house.png`를 집 꾸미기 버튼 슬롯에 연결
- 집 꾸미기 버튼의 최소 44px 터치 높이 보장
- 사용자 제공 초안인 `교감하기` 문구를 공용 상수로 관리
- 실제 집 화면과 배경 테스트 화면의 문구·접근성 라벨 동기화
- 집 화면 컴포넌트 회귀 테스트 보강

## 제외 범위

- 친밀도 적립량·횟수 제한·퀘스트 규칙 변경
- 아이템 구매 및 배경 선택 로직 변경
- 신규 디자인 자산 생성 또는 기존 이미지 편집
- 백엔드 및 공개 API 변경

## 인수 조건

1. 집 꾸미기 버튼에 사용자 제공 이미지가 표시된다.
2. 버튼의 터치 높이가 44px 이상이다.
3. 교감 관련 문구와 접근성 라벨이 공용 문구와 일치한다.
4. 마스코트 반응과 친밀도 로직은 바뀌지 않는다.
5. 포맷, 린트, 타입 검사, 관련 테스트와 프로덕션 빌드가 통과한다.

## 변경 예상 파일

- `frontend/src/assets/house/zip_ggumigi/house.png`
- `frontend/src/assets/index.ts`
- `frontend/src/features/house/houseArtSlots.ts`
- `frontend/src/features/house/houseModel.ts`
- `frontend/src/features/house/MascotHouseContent.tsx`
- `frontend/src/features/house/BackgroundTestContent.tsx`
- `frontend/tests/MascotHouseScreen.test.tsx`
- `frontend/tests/AssetFoundation.test.ts`
- 이 문서

## API 영향

없음.

## DB·마이그레이션 영향

없음.

## 안전·개인정보·보안 영향

건강·개인정보를 새로 수집하거나 저장하지 않는다. 운동 미수행을 탓하거나 재촉하는 문구를
추가하지 않는다.

## 선행 관계와 차단 요소

선행 작업은 없다. 공유된 Claude artifact는 현재 직접 열 수 없어, 저장소에 제공된 이미지와
미커밋 문구 초안을 사용자 제공 기준으로 인수한다.

## 테스트 계획

- Prettier
- ESLint
- TypeScript typecheck
- `tests/houseModel.test.ts`
- `tests/MascotHouseScreen.test.tsx`
- 프로덕션 빌드

## 수동 확인

`npm.cmd run web` 실행 후 `/?preview=mascot-house`에서 집 꾸미기 아이콘, 터치 영역,
교감 안내와 퀘스트 문구를 확인한다.

## 알려진 제한과 후속 작업

`교감하기`와 `house.png`는 사용자 제공 초안 기준이다. Claude artifact와의 픽셀 단위 대조는
링크 접근이 복구된 뒤 후속 확인이 필요하다. FE-12도 `MascotHouseContent.tsx`를 수정하므로 두
PR 중 나중에 병합되는 브랜치는 `develop` 재기반 후 충돌을 수동으로 확인한다.
