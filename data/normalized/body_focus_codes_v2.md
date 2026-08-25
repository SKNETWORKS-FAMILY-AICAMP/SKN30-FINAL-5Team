# body-focus-v2 코드 목록

## 목적과 적용 범위

`body_focus_code`는 운동 하나를 조회·집계할 때 쓰는 단일 대표 훈련 초점 코드다. 주동근·보조근의
상세 관계는 `catalog_enrichment_v2.csv`의 `primary_body_area_codes`·
`secondary_body_area_codes`에 JSON 배열로 보존하며, 이 코드는 그것을 대체하지 않는다. 원천의
복수 근육 표현은 `data/reports/integrated_exercise_review_updated.csv`에 그대로 둔다.

생성 카탈로그는 `training_type_code`에 `STRENGTH`, `CARDIO`, `MOBILITY`만 저장한다.
`CARDIO` 운동의 대표 초점은 항상 `CARDIO`, `MOBILITY` 운동의 대표 초점은 항상 `MOBILITY`다.
`STRENGTH` 운동만 대표 주동근군 하나를 아래 코드에서 선택한다.

## 허용 코드

| 그룹 | 코드 | 한글 표시명 | 정의·선택 기준 |
|---|---|---|---|
| 상체 | `CHEST` | 가슴 | 대흉근 중심의 수평 밀기·플라이·체스트 프레스 |
| 상체 | `BACK` | 등 | 광배근·승모근·척추기립근·상부 등 중심의 당기기·신전 |
| 상체 | `SHOULDERS` | 어깨 | 삼각근 중심의 프레스·레이즈·리어델트 동작 |
| 상체 | `BICEPS` | 이두근 | 상완이두근 중심의 컬·당기기 보조보다 직접 자극이 주목적인 동작 |
| 상체 | `TRICEPS` | 삼두근 | 상완삼두근 중심의 익스텐션·푸시다운·좁은 밀기 |
| 상체 | `FOREARMS` | 전완 | 손목 굴곡·신전·그립 중심의 전완 동작 |
| 하체 | `GLUTES` | 둔근 | 둔근이 대표 초점인 힙 힌지·브리지·런지 |
| 하체 | `QUADRICEPS` | 대퇴사두근 | 무릎 폄·스쿼트 계열에서 대퇴사두근이 대표 초점인 동작 |
| 하체 | `HAMSTRINGS` | 햄스트링 | 무릎 굽힘·루마니안 데드리프트 등 햄스트링이 대표 초점인 동작 |
| 하체 | `CALVES` | 종아리 | 발바닥 굽힘·카프 레이즈·카프 프레스 |
| 몸통/기타 | `CORE` | 코어 | 복부·복횡근·복사근 중심의 브레이싱·크런치·회전 제어 |
| 몸통/기타 | `FULL_BODY` | 전신 | 특정 부위 하나가 대표적이지 않고 전신 협응이 훈련 초점인 근력 동작에만 사용 |
| 유산소·가동성 | `CARDIO` | 유산소 | 걷기·달리기·점프 등 심폐·지속 활동; `training_type_code=CARDIO`에 고정 |
| 유산소·가동성 | `MOBILITY` | 가동성 | 스트레칭·관절 가동성 활동; `training_type_code=MOBILITY`에 고정 |

다음은 저장할 수 없다: 복수값, 쉼표, `|`, 공백, 한글, 자유 텍스트, `UNSPECIFIED`,
`UPPER_BODY`, `LOWER_BODY`.

## 매핑과 검토 상태

단일 Source of Truth는 `catalog_enrichment_v2.csv`다. 각 `exercise_id`는 정확히 한 개의
`body_focus_code`, 매핑 근거와 상태를 가진다. 원천 근육이 복수이거나 원천 target과 후보가
충돌해 확정할 수 없으면 `proposed_body_focus_code`에 단일 제안 코드를 기록하고
`body_focus_status=REVIEW_REQUIRED`로 둔다. `body_focus_mapping_v2.csv`는 초기 작업표
생성 전의 보존 입력이며, 최종 생성기는 읽지 않는다.

`APPROVED`는 `body_focus_basis`, 비식별 `reviewer`, timezone이 포함된 ISO 8601 `reviewed_at`가
모두 있을 때만 허용된다. 검토 전 행은 `APPROVED`, `READY_FOR_MEDIA`, `DOMAIN_APPROVED`로
승격하지 않는다. 생성기는 `REVIEW_REQUIRED` 매핑이 하나라도 있는 운동을
`REVIEW_REQUIRED_BODY_FOCUS` 상태로 출력한다.

## 기존 코드 전환표

| 중단 코드 | 전환 원칙 | 새 코드 |
|---|---|---|
| `UPPER_BODY` | 원천 대표 주동근 또는 대표 훈련 초점을 세분화 | `CHEST`, `BACK`, `SHOULDERS`, `BICEPS`, `TRICEPS`, `FOREARMS`, `CORE`, `FULL_BODY` 중 하나 |
| `LOWER_BODY` | 원천 대표 주동근 또는 대표 훈련 초점을 세분화 | `GLUTES`, `QUADRICEPS`, `HAMSTRINGS`, `CALVES`, `CORE`, `FULL_BODY` 중 하나 |

`UPPER_BODY`와 `LOWER_BODY`를 기계적으로 하나의 고정 코드로 치환하지 않는다. 각 운동의
매핑 근거와 검토 상태를 확인해 단일 대표 코드를 선택한다.

출처: `data/normalized/catalog_enrichment_v2.csv`,
`data/reports/integrated_exercise_review_updated.csv`의 `training_type_code_candidate`, `target`,
`source_target`; `docs/DATA_MODEL.md` §5.2·§5.4.
