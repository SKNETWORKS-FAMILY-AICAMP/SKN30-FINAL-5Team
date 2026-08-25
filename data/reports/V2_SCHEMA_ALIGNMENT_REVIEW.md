# V2 최종산출물 스키마 정합성 검토

검토 기준은 `backend/app/modules/catalog/schemas.py`의 입력 Pydantic 계약과
`docs/DATA_MODEL.md`의 논리 모델이다. V1 산출물은 비교 대상에서 제외한다.

## 1. 이번 생성기에서 컬럼명이 정렬된 항목

의미와 타입이 스키마와 일치하는 중복 컬럼은 서비스 스키마 이름으로 통일한다. 원천명처럼 의미가
다른 컬럼과 FITT·검토용 컬럼은 유지한다.

| 산출물 | 기존 컬럼 | 최종 컬럼 | 판정 |
|---|---|---|---|
| 대표운동 | `exercise_name_ko` | `name_ko` | 동일 의미·동일 타입 |
| 대표운동 | `exercise_name_en` | `name_en` | 동일 의미·동일 타입 |
| 대표운동 | `target_muscle` | `body_focus_code` | 동일 코드값·서비스 명칭으로 정렬 |
| 대표운동 | `movement_pattern_code` | `primary_movement_pattern_code` | 동일 코드값·서비스 명칭으로 정렬 |
| 대표운동 | `fitt_timing_mode_code` | `timing_mode_code` | 동일 코드값·서비스 명칭으로 정렬 |
| 대체운동 | `goal_code` | `goal_preservation_code` | 목표 보존 의미로 정렬 |
| 안전규칙 | `movement_pattern` | `movement_pattern_code` | 동일 패턴 코드 |
| 안전규칙 | `body_area` | `body_area_code` | 동일 부위 코드 |
| 안전규칙 | `action` | `effect_code` | `EXCLUDE`/`CAUTION` 동일 코드 |
| 안전규칙 | `reason` | `reason_code` | 동일 근거 코드 |

대표운동의 `source_name`은 원천 표시명이 한글·영문 어느 쪽이든 보존하기 위한 공통 원천명이다.
`source_name_en`은 영문 원천명이 확인될 때 별도로 유지한다.

## 2. 데이터 담당자에게 요청할 추가·보완 컬럼

### 대표운동

- `stable_code`: `^[a-z0-9_]+$` 형식의 서비스용 안정 코드. 현재 `REX-######`은 review ID로만 보존한다.
- `beginner_suitable`: `true/false` 확정값
- `location_codes`: `HOME`, `GYM`, `OUTDOOR` 중 하나 이상
- `recovery_eligible`: 회복안 후보 여부
- `default_seconds_per_rep` 또는 `default_work_seconds`: `timing_mode_code`에 따른 단일 정수값
- `default_rest_seconds`, `default_transition_seconds`: 단일 정수값
- `instruction_summary_ko`, `form_cues_ko`, `instruction_content_version`
- `source_track`, `source_identity`
- `review_status_code`: 최종 운영 검수 상태

`source_track` 원천 코드는 `wger`, `kspo`, `gymvisual`을 사용한다. 운동 레코드는 원래
원천 코드를 유지하며, 여러 원천을 묶은 카탈로그 컨테이너에만 `merged`를 사용한다. `merged`를
운동 레코드의 `source_track` 대신 입력하지 않는다.

현재 `fitt_default_sets/reps/work_seconds/rest_seconds/transition_seconds`는 `2-3`, `8-12`,
`15-30` 같은 범위 문자열이므로 DB 입력 정수 컬럼으로 직접 적재할 수 없다. 범위값은 FITT 검토자료로
보존하고, 서비스 처방용 단일값은 별도 확정해야 한다.

`equipment_codes`는 사용자가 준비해야 하는 주 장비 제약으로 해석한다. V2 신규 산출물에서는
`BENCH`, `CHAIR`를 사용하지 않고, 의자·벤치가 필요한 조건은 수행 안내와 설치 조건에 기록한다.
기존 코드 자체를 삭제하지 않고 V2 사용만 중단한다.

V2 장비 정규화 기준은 다음과 같다.

| V2 현재 값 | 최종 코드 | 처리 |
|---|---|---|
| `CABLE` | `CABLE_MACHINE` | 명칭 정렬 |
| `CABLE|MACHINE` | `CABLE_MACHINE` | 최종 원본 검수값으로 통합 |
| `BAND` | `RESISTANCE_BAND` | 명칭 정렬 |
| `ROPE` | `STRETCH_STRAP` | 스트레칭 용도로 의미 명확화 |
| `ROLLER` | `FOAM_ROLLER` | 신규 코드 검토 |
| `WEIGHTED` | `HOUSEHOLD_WEIGHT` | 최신 원본 검수값 적용 |
| `BENCH`, `CHAIR` | 사용 중단 | 수행 안내에만 지지물로 기록 |

`PULL_UP_BAR`, `RESISTANCE_BAND`, `STRETCH_STRAP`은 유지한다. `PULL_UP_BAR`는 풀업·스캐풀라 풀업에
복원하고, 스트레치 스트랩 미보유 시에는 `BODYWEIGHT` 대체운동으로 전환한다. `REX-000094`은
`STRETCH_STRAP` 기본값으로 두고 `RESISTANCE_BAND` variant는 별도 검수한다.

`REX-000049` 시티드 체스트 프레스는 벤치 자체가 아닌 시티드 체스트 프레스 머신으로 정렬한다.

```text
representative_exercise_id: REX-000049
name_ko: 시티드 체스트 프레스
equipment_codes: ["MACHINE"]
primary_movement_pattern_code: HORIZONTAL_PUSH
location_codes: ["GYM"]
```

### Movement pattern v2 승인 코드셋

V2가 사용하는 다음 15개를 승인 코드셋으로 확정한다. 기존 코드는 유지하고 `BALANCE`, `CYCLING`,
`ELLIPTICAL`, `JUMP_PLYOMETRIC`을 additive로 추가한다.

```text
BALANCE, CORE_BRACE, CYCLING, ELLIPTICAL, GAIT,
HIP_DOMINANT, HORIZONTAL_PULL, HORIZONTAL_PUSH, ISOLATION,
JUMP_PLYOMETRIC, KNEE_DOMINANT, KNEE_FLEXION, MOBILITY_STRETCH,
VERTICAL_PULL, VERTICAL_PUSH
```

### 대체운동

- `source_exercise_id`, `alternative_exercise_id`: 서비스 운동 FK 또는 유효한 `stable_code` 매핑
- `reason_code`: `EQUIPMENT`, `LOCATION`, `DIFFICULTY`, `DISCOMFORT` 중 구조화된 값
- `difficulty_delta`: `-1` 또는 `0`
- `rule_version`, `alternative_set_version_code`
- `review_status_code`: `DOMAIN_APPROVED` 여부
- `production_eligible`
- `source_manifest_hash`, `source_metadata`, `created_at`

현재 `relationship_type`의 `CONSTRAINT`, `INTENSITY`, `RECOVERY`, `SAFETY`는 DB `reason_code`와
일대일 대응하지 않는다. 임의 매핑하지 말고 데이터 담당자가 관계별 운영 사유를 확정해야 한다.

대체운동에는 안전규칙 재검증을 위해 다음 부위 컬럼을 추가한다. 이는 근육명 자체가 아니라
서비스 안전규칙이 사용하는 `body_area_code`의 원본·대체 양끝 값이다.

- `source_primary_body_area_codes`, `source_secondary_body_area_codes`
- `alternative_primary_body_area_codes`, `alternative_secondary_body_area_codes`

### 안전규칙

- `body_part_role_code`: `PRIMARY` 또는 `SECONDARY`
- `rule_scope`: `EXERCISE` 또는 `MOVEMENT_PATTERN`
- `exercise_stable_code` 또는 `movement_pattern_code` 중 정확히 하나
- `minimum_severity_code`, `maximum_severity_code`
- `rule_version`, `rule_set_version_code`
- `review_status_code`: `DOMAIN_APPROVED` 여부
- `production_eligible`
- `source_manifest_hash`, `source_metadata`, `created_at`, `updated_at`

대표운동의 `primary_body_area_codes`, `secondary_body_area_codes`와 위 대체운동 양끝 부위 컬럼은
안전규칙 매핑의 입력으로 사용한다. 현재 V2 JSONL의 `pain_level`과 `pain_score_decisions`는 검토용 정책자료로 보존한다. 런타임 입력에는
최소·최대 심각도 컬럼을 별도로 채워야 한다. `LEGACY_EXERCISE_SCOPE` 및 미매핑 legacy rule은
대상 운동이 확정되기 전까지 적재 대상이 아니다.

### 산출물 작성값·importer 파생값·DB 생성값 구분

| 구분 | 대표 값 | 책임 경계 |
|---|---|---|
| 산출물 작성값 | `stable_code`, `source_track`, `source_identity`, 운동·대체·안전규칙의 구조화된 의미값, `review_status_code`, `rule_version` | 원천·도메인 검수 근거로 확정하며 importer가 임의로 추정하지 않는다. |
| importer 파생값 | `catalog_version_id`, 운동 FK, `alternative_set_version_code`, `rule_set_version_code`, `production_eligible`, `source_manifest_hash`, `source_metadata` | stable code·manifest·승인 registry를 검증해 생성한다. `production_eligible`은 `review_status_code`와 별도로 version·hash·count가 모두 일치할 때만 `true`다. |
| DB 생성값 | `id`, 대표운동·안전규칙의 `created_at`, `updated_at` | DB default나 영속화 계층이 생성하며 데이터 담당자가 임의로 채우지 않는다. |

단, 대체운동의 `created_at`은 현재 `ExerciseAlternativeRecord` 입력 계약에서 timezone이
포함된 필수값이므로 대체운동 bundle 생성 단계에서 기록한다. 이 시각은 도메인 판단값이
아니며, 승인 상태나 원천 시각을 추정하는 용도로 사용하지 않는다.

## 3. 필수 컬럼 확인 결과

현재 V2 최종본은 대표운동 102건, 대체관계 116건, 안전규칙 384건을 생성하지만, 위 추가 컬럼이
없어 현재 서비스 입력 스키마를 완전히 통과하지 않는다. 생성기 정렬은 완료했으며, 누락값을 추정해
운영 데이터로 승격하지 않는다.

### 3.1 스키마와 산출물 모두에 없어 생성해야 하는 필수값

다음은 기존 산출물의 다른 컬럼으로 대체할 수 없다.

- 대표운동: 유효한 `stable_code`, `location_codes`, `beginner_suitable`, `recovery_eligible`,
  단일 정수형 시간값, 수행 안내 콘텐츠, `source_track`, `source_identity`, 최종 `review_status_code`
- 대체운동: 양 끝점의 서비스 운동 ID 매핑, `difficulty_delta`, 구조화된 `reason_code`, 관계·규칙 버전,
  최종 `review_status_code`, `source_manifest_hash`, `source_metadata`, `created_at`
- 안전규칙: `body_part_role_code`, 정확한 `rule_scope`, 운동 또는 패턴 대상, 최소·최대 심각도,
  규칙 세트 버전, 최종 `review_status_code`, `source_manifest_hash`, `source_metadata`, 생성·수정 시각

`id`, `catalog_version_id`, 대표운동·안전규칙의 `created_at`, `updated_at`처럼 입력
스키마에는 없고 DB에 필요한 값은 데이터 담당자가 임의로 채우는 값이 아니라
importer·DB가 생성해야 하는 운영 컬럼이다. 대체운동의 `created_at`은 위 입력 계약 예외를
따른다.

### 3.2 JSON 산출 전 권장 작업 순서

다음 순서로 확정·변환한 뒤 JSON을 산출한다.

1. 스키마 계약 확정, backend 반영 및 CSV 재생성 필요
2. 대표운동 필수값 확정
3. 대체운동 관계 정리
4. 안전규칙 운영 레코드 변환
5. manifest 생성 및 fail-closed 검증

이 순서는 문서 작성 순서가 아니라 CSV·생성기·스키마·JSON을 실제로 수정하고 재생성하는
실행 순서다. **도메인 검수는 완료됐고, 백엔드 코드·생성기·V2 CSV에도 반영됐다.** 여기서
남은 것은 검수 완료값의 JSONL 구조화·manifest 검증과 운영 eligibility 계산이다.

대체관계와 안전규칙은 대표운동의 `stable_code`, 난이도, 신체 부위에 의존하므로 대표운동을
먼저 확정한다. 대표운동이 확정되지 않은 상태에서는 대체관계나 안전규칙의 누락값을 추정해
운영 레코드로 승격하지 않는다.

### 3.3 대표운동 필수값 확정

도메인 검수 상태: **완료**. 아래 절차는 새로운 도메인 판단을 요청하는 단계가 아니라, 확정된
판단을 서비스 입력 컬럼과 산출물에 옮기는 materialization 단계다.

#### 권장 절차

1. `REX-######`과 별도로 변경하지 않는 `stable_code` registry를 생성한다.
2. 선정 NEX를 기준으로 최신 원본의 `source_track`, `source_identity`, 장소·라이선스 연결을
   확정한다.
3. 장비·장소를 허용 코드의 JSON 배열로 정규화한다.
4. `beginner_suitable`, `recovery_eligible`을 `bool`로 검수한다.
5. FITT 범위값과 별도로 런타임에서 사용할 단일 정수값을 확정한다.
6. 수행 콘텐츠를 검수하고 `instruction_content_version`을 부여한다.
7. 최종 `review_status_code`를 기록한다.

#### 권장 해결안

- `stable_code`는 family 기반 영문 코드에 필요한 장비·동작 구분자를 추가하고 이후 변경하지
  않는다.
- `CONDITIONAL`, `NOT_PRIORITY`, `REVIEW_REQUIRED`는 bool로 자동 변환하지 않는다.
- FITT 범위의 중간값을 자동 선택하지 않고 family별 단일값 기준을 별도로 승인한다.
- 도메인 검수 완료 증적을 보존하되, importer가 상태 문자열만으로 `DOMAIN_APPROVED` 또는
  `production_eligible=true`를 자동 부여하지 않는다.

#### 완료 조건

- 102개 `stable_code`가 모두 고유하다.
- 필수값과 배열 컬럼이 유효하다.
- 런타임 값에 `UNSPECIFIED`, `REVIEW_REQUIRED`가 없다.
- 승인자·검수시각·콘텐츠 버전이 존재한다.

### 3.4 대체운동 관계 정리

#### 실제 수정 대상

- `data/scripts/build_final_exercise_catalog_v2.py`
- `data/generated/exercise-alternatives-v0.3.0/alternative_relationships.csv`의 생성 원본
- 대표운동 `stable_code` registry와 대체관계 입력 계약

#### 실행 기준

1. NEX 관계를 REX 양끝점으로 해석하고 동일한 REX·대체 NEX·관계 유형의 중복을 통합한다.
2. 대표운동의 `stable_code`, 난이도, movement pattern, 신체 부위를 양끝에서 재검증한다.
3. `difficulty_delta`는 `-1` 또는 `0`으로 확정하고, `relationship_type`을 임의로
   `reason_code`에 매핑하지 않는다.
4. 운영 `reason_code`는 `EQUIPMENT`, `LOCATION`, `DIFFICULTY`, `DISCOMFORT` 중 하나로
   관계 사유를 검수해 기록한다.
5. 스트랩 미보유 조건은 `STRETCH_STRAP` 관계와 맨몸 대체운동 연결을 별도 검수해 기록한다.
6. `review_status_code`, `rule_version`, `alternative_set_version_code`,
   `source_manifest_hash`, `source_metadata`, `created_at`을 채우고, 승인 전에는
   `production_eligible=false`로 유지한다.

대체운동은 대표운동이 확정된 뒤에만 생성한다. 원본 CSV를 직접 손으로 수정하지 않고 관계
생성기와 입력 원본을 수정한 뒤 재생성한다.

### 3.5 안전규칙 운영 레코드 변환

#### 실제 수정 대상

- `data/scripts/build_safety_rules_v2.py`
- `data/generated/exercise-safety-rules-v2.0.0/safety_rules_v2.jsonl`
- `data/generated/exercise-safety-rules-v2.0.0/exercise_safety_mapping_v2.csv`의 생성 원본
- 대표운동 `stable_code` registry와 안전규칙 mapping 입력

#### 실행 기준

1. `rule_scope`를 `EXERCISE` 또는 `MOVEMENT_PATTERN`으로 확정하고, 대상은 정확히 하나만
   지정한다.
2. 대표운동 대상은 `exercise_stable_code`, 패턴 대상은 `movement_pattern_code`를 사용한다.
3. `body_part_role_code`, `minimum_severity_code`, `maximum_severity_code`, `effect_code`,
   `reason_code`를 런타임 컬럼으로 변환한다. `pain_level`과 `pain_score_decisions`는
   검토 자료로만 보존한다.
4. 대표운동의 primary·secondary 신체 부위와 대체관계 양끝 부위를 사용해 mapping을
   재검증한다.
5. `rule_version`, `rule_set_version_code`, `source_manifest_hash`, `source_metadata`,
   `created_at`, `updated_at`을 기록한다.
6. 도메인 검수는 완료 상태로 기록하되, 운영 필수 컬럼·manifest·승격 조건이 충족되기 전까지
   `production_eligible=false` 및 비활성 상태로 유지한다.

안전규칙도 생성기에서 재생성하며, 도메인 검수 완료 사실과 운영 승격 조건을 혼동하지 않는다.
대상 운동이 확정되지 않은 `LEGACY_EXERCISE_SCOPE`와
미매핑 legacy rule은 적재하지 않는다.

### 3.6 JSON·manifest 검증

#### 실제 수정 대상

- importer 입력 계약(`backend/app/modules/catalog/schemas.py`)
- 대표운동·대체운동·안전규칙 JSONL generator
- 각 산출물 manifest와 fail-closed 검증 테스트

#### 실행 기준

1. 대표운동 JSONL은 `ExerciseRecord`, 대체운동 JSONL은 `ExerciseAlternativeRecord`,
   안전규칙 JSONL은 `ExerciseSafetyRuleRecord`로 Pydantic 검증한다.
2. 대표운동 102건의 `stable_code` 고유성, 필수값, 배열 코드, 런타임 단일 정수값을 검증한다.
3. 대체관계의 양끝점·사유·난이도 변화·버전·생성시각과 안전규칙의 대상·severity 범위·버전을
   검증한다.
4. 각 manifest에 입력·산출물의 SHA-256, 바이트 수, 레코드 수, generator version,
   code-set version, policy/review 상태를 기록한다.
5. 해시·건수·버전·Pydantic 검증 중 하나라도 불일치하면 산출물을 운영용으로 생성하거나
   승격하지 않고 실패한다.

도메인 검수는 완료됐다. 검증을 통과한 산출물은 JSONL로 구조화할 수 있지만, 운영 필수값·권리
검수·manifest 승격 조건이 충족되기 전까지 `production_eligible=false`다. 즉
`DOMAIN_APPROVED`는 도메인 검수 완료 증적이고 운영 공개·적재 승인을 뜻하지 않는다.
생성된 CSV·JSONL을 직접 수정하지 않고 입력 원본과 생성기를 수정해 다시 만든다.

현재 실행 결과는 대표운동 CSV 102건, 대체관계 116건, 안전규칙 원본 384건, runtime 안전규칙
394건과 stable code registry를 재생성했으며, 대표운동의 `beginner_suitable`,
`recovery_eligible`, 수행 콘텐츠, `review_status_code`, 런타임 단일 시간값이 모두 채워져
runtime JSON 산출 자격은 `true`다.
도메인 검수 상태는 **완료**다. 다만 권리·운영 승격 조건은 별도이므로 runtime manifest의
`production_eligible`은 `false`로 유지하고, JSONL을 운영 공개·적재하지 않는다.

## 4. 미디어 저장 경계

미디어 바이너리와 운영 메타데이터는 로컬 저장소·로컬 DB에 적재하지 않는다. AWS 관리형 미디어
저장소/DB가 소유하며, V2 로컬 산출물은 권리 승인 전까지 빈 미디어 레지스트리와 외부 자산 참조
정책만 보존한다. 권리 승인 후에도 서비스 카탈로그에는 외부 자산 키만 연결한다.

출처:

- `docs/DATA_MODEL.md` §5.2, §5.8, §5.9
- `backend/app/modules/catalog/schemas.py`의 `ExerciseRecord`, `ExerciseAlternativeRecord`, `ExerciseSafetyRuleRecord`
- `backend/app/modules/catalog/codes.py`의 카탈로그 코드셋
- `backend/app/db/models/catalog.py`의 `Exercise`, `ExerciseAlternative`, `ExerciseSafetyRule`
- `data/generated/exercise-catalog-v2.0.0-final/representative_exercises_v2_final.csv`
- `data/reports/integrated_exercise_review_updated.csv`의 선정 NEX 원천 정보
