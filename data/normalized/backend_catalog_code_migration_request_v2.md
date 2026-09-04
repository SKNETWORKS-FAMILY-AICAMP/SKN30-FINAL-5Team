# 백엔드 적용 요청서: 통합 운동 카탈로그 코드 v2

## 요청 및 v2.0.6 적용 상태

카탈로그 importer와 API/DB lookup의 허용값을 다음으로 맞춰 주세요.

- `training_type_code`: `STRENGTH`, `CARDIO`, `MOBILITY`
- `body_focus_code`: `CHEST`, `BACK`, `SHOULDERS`, `BICEPS`, `TRICEPS`, `FOREARMS`, `GLUTES`, `QUADRICEPS`, `HAMSTRINGS`, `CALVES`, `CORE`, `FULL_BODY`, `CARDIO`, `MOBILITY`

v2.0.6 237행 backend projection을 위해 `ADDUCTORS`를 기존 코드셋에 additive하게 추가했다.
기존 legacy 값은 치환하지 않는다.

생성 입력은 `data/normalized/body_focus_mapping_v2.csv`, 코드 정의는
`data/normalized/body_focus_codes_v2.md`, 생성 출력은
`data/generated/exercise-catalog-v1.0.0(팀원 검토 예정)/exercise_catalog_v1.csv`입니다.

## 적용 조건

- 생성 CSV의 `exercise_type`은 `training_type_code`로, `focus`는 `body_focus_code`로 교체됐다.
- `body_focus_code`는 운동당 하나의 대표 초점일 뿐, `exercise_body_parts`의 PRIMARY/SECONDARY
  관계를 대체하지 않는다.
- `UPPER_BODY`, `LOWER_BODY`, `UNSPECIFIED`, 복수 구분자 값은 importer에서 거부한다.
- `mapping_status=REVIEW_REQUIRED`인 208개 행은 사용자 노출·활성 카탈로그로 승격하면 안 된다.
  이 산출물은 `REVIEW_REQUIRED_BODY_FOCUS` 상태다.
- `APPROVED` 매핑에는 매핑 근거, 비식별 검토자 참조, timezone 포함 검토일이 필수다.

## 호환성·승인 필요사항

현재 API 계약과 데이터 모델에는 `UPPER_BODY`, `LOWER_BODY` 예시가 남아 있으므로, 기존 공개
응답 소비자와 DB lookup 변경은 백엔드·프론트엔드·개발 리드의 계약 검토 후 additive migration
또는 versioned code-set으로 적용해야 합니다. 이 데이터 변경은 API field 삭제나 DB migration을
포함하지 않습니다.

## 수용 테스트

1. importer가 15개 body-focus-v2 코드와 세 가지 training type만 허용한다.
2. 빈값, 미등록 코드, 한글·`UNSPECIFIED`·기존 상/하체 코드, 쉼표·`|`·공백 포함 값은 실패한다.
3. `APPROVED` 매핑에서 근거·검토자·검토일 하나라도 없으면 실패한다.
4. 검토대기 행을 import해도 `READY_FOR_MEDIA` 또는 활성/도메인승인 상태가 되지 않는다.

## 세부 코드와 legacy DB 값의 호환 전략

정규화 데이터는 `ADDUCTORS`를 포함한 15개 세부 body-focus 코드를 보존한다. 기존 DB에
남아 있는 `UPPER_BODY`·`LOWER_BODY`는 이미 저장된 legacy 값이므로 이번 data 작업에서
직접 치환하지 않는다. 구체 코드를 DB에서 실제 조회·추천에 사용하려면 다음을 별도
백엔드 작업으로 수행해야 한다.

1. `body_focuses` lookup과 backend enum/검증기의 additive code-set에 `ADDUCTORS`를 추가한다.
2. catalog-v2 taxonomy registry hash와 importer 계약을 갱신한다.
3. 기존 legacy 행은 보존하고, 새 catalog-v2 행부터 세부 코드를 적재한다.
4. 기존 `UPPER_BODY`·`LOWER_BODY` 행은 근거가 확인된 경우에만 개별 backfill하고, 불명확한
   행은 강제 변환하지 않는다.
5. API·프론트 필터·집계는 세부 코드와 legacy 상·하체 roll-up을 함께 지원한다.

따라서 v2.0.6부터 새 catalog row는 `ADDUCTORS`를 포함한 세부 코드를 사용하고, 기존
legacy 행은 보존한다. DB 컬럼 구조를 바꾸는 migration은 필요하지 않으며, runtime/API
허용 enum과 importer 계약의 additive 변경만 적용한다.

출처: `docs/API_CONTRACT.md` §8·§19, `docs/DATA_MODEL.md` §5.1~§5.4,
`data/normalized/body_focus_codes_v2.md`.
