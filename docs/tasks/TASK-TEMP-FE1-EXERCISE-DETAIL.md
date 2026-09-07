# TASK-TEMP-FE1-EXERCISE-DETAIL

## 상태

- 구현 완료
- 브랜치: `feat/temp-fe1-exercise-detail`
- 기준: `origin/develop` (`2ef5d75`)

## 목표

BM-2가 추가한 운동 상세 계약을 사용해 주요 부위, 단계별 자세 설명, 주의사항 순서로 표시하고 승인된 생활도구 안내를 노출한다.

## 변경 계획

1. 프론트 응답 타입에 additive 상세 필드와 생활도구 가이드 타입을 추가한다.
2. 운동 상세 시트에서 서버가 분리한 단계와 주의사항을 표시하되 구버전 응답은 기존 필드로 폴백한다.
3. 생활도구 제안, 예시, 주의사항을 별도 안내 카드로 표시한다.
4. 프리뷰와 컴포넌트 테스트를 갱신하고 전체 프론트 검증을 수행한다.

## 위험 및 호환성

- 프론트에서 `instruction_summary`를 파싱하지 않는다.
- 신규 응답 필드는 구버전 서버·목과 호환되도록 optional read 타입으로 둔다.
- GIF 로딩 및 오류 처리는 변경하지 않는다.
- API, 데이터베이스, 안전 판단 로직을 변경하지 않는다.

## 검증 결과

- `npm.cmd run format:check`: 통과
- `npm.cmd run lint`: 통과
- `npm.cmd run typecheck`: 통과
- `npm.cmd test -- --runInBand tests/ExerciseDetailSheet.test.tsx tests/GapClosureScreens.test.tsx`: 2 suites, 18 tests 통과
- `npm.cmd run build:production`: Android/iOS export 통과 (최초 sandbox 실행은 Hermes `spawn EPERM`, 권한 허용 재실행 성공)
- 전체 `npm.cmd test -- --runInBand`: 33 suites 중 32 suites, 550 tests 중 549 tests 통과. FE-1과 무관한 기존 `PreviewGallery`의 1초 비동기 대기 테스트가 실행마다 다른 케이스에서 간헐 실패했다. FE-1 관련 suite는 전체 실행에서도 통과했다.

## 남은 확인

- 프리뷰에서 의자 스쿼트 상세를 열어 주요 부위 → 자세 설명 → 주의사항 → 생활도구 안내 순서와 작은 화면 스크롤을 수동 확인한다.
- `PreviewGallery` 비동기 대기 안정화는 FE-1 범위 밖의 기존 테스트 부채로 별도 처리한다.
