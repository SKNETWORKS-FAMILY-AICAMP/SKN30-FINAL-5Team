# TASK-TEMP-FE1-EXERCISE-DETAIL

## 상태

- 구현 완료
- 브랜치: `feat/temp-fe1-exercise-detail`
- 기준: `origin/develop` (`905d263`)

## 목표

BM-2와 통합 카탈로그가 추가한 운동 상세 계약을 사용해 대표 초점, 세부 부위,
단계별 자세 설명, 주의사항 순서로 표시하고 운동 장소에 맞는 승인 장비 안내만
노출한다.

## 변경 계획

1. 프론트 응답 타입에 `body_focus_code`와 gym/home 장비 가이드를 additive 필드로 추가한다.
2. 목록과 상세에 서버의 단일 대표 초점을 표시하고, 기존 `primary_body_area_codes`는
   세부 부위로 유지한다.
3. 장소 컨텍스트에 따라 home/gym 안내를 구분하고, 호출자가 장비 코드를 제공하면
   해당 코드의 안내만 표시한다. gym 시작 무게는 참고값으로 명시한다.
4. 새 필드와 컨텍스트가 없을 때 기존 상세 표시가 유지되는지 테스트한다.
5. 프리뷰와 컴포넌트 테스트를 갱신하고 전체 프론트 검증을 수행한다.

## 위험 및 호환성

- 프론트에서 `instruction_summary`를 파싱하지 않는다.
- 신규 응답 필드는 구버전 서버·목과 호환되도록 optional read 타입으로 둔다.
- `ExerciseGuideContext`의 `locationCode`가 없거나 HOME/GYM이 아니면 잘못된 장소 안내를
  노출하지 않는다. `availableEquipmentCodes`가 명시되면 해당 코드로 추가 필터링한다.
- 현재 운동 계획 항목은 사용 가능 장비 코드를 내려주지 않는다. 따라서 장비 목록을
  넘기지 않은 호출자는 백엔드가 해당 운동으로 스코핑한 가이드를 신뢰한다.
- GIF 로딩 및 오류 처리는 변경하지 않는다.
- API, 데이터베이스, 안전 판단 로직을 변경하지 않는다.

## 검증 결과

- `npm.cmd run format:check`: 통과
- `npm.cmd run lint`: 통과
- `npm.cmd run typecheck`: 통과
- `npm.cmd test -- --runInBand tests/ExerciseDetailSheet.test.tsx tests/GapClosureScreens.test.tsx`:
  2 suites, 21 tests 통과. 기존 AccountScreen 비동기 `act(...)` 경고가 출력되지만 실패는 아니다.
- 프로덕션 export: Android/iOS 모두 통과. 공유 `node_modules/.bin/expo.cmd` 누락으로
  `npm.cmd run build:production`은 CLI 실행 전 실패했고, 같은 설치된 CLI의 실제 엔트리인
  `node node_modules/expo/bin/cli export --platform android|ios ...`로 각 플랫폼을 검증했다.
  샌드박스의 Hermes `spawn EPERM`은 권한 허용 재실행으로 해소했고, iOS 최초
  `ENOSPC`는 FE-1 Android 생성물을 정리한 후 재실행해 통과했다. 최종 생성물은 디스크
  공간 회수를 위해 삭제했다.

## 남은 확인

- FE-2가 운동 세션의 `locationCode`를 이어줄 때 `WorkoutScreen.exerciseGuideContext`로
  `{ locationCode, availableEquipmentCodes? }`를 전달한다. 현재 Home 상세는 저장된 체크인 장소를
  이미 전달한다.
- 프리뷰에서 대표 초점, HOME 생활도구, GYM 시작 안내와 작은 화면 스크롤을 수동 확인한다.
- `PreviewGallery` 비동기 대기 안정화는 FE-1 범위 밖의 기존 테스트 부채로 별도 처리한다.
