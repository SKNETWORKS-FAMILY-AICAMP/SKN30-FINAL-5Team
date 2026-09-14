# 통합 운동 카탈로그 후속 인계

작성일: 2026-09-07  
기준 번들: `integrated-catalog-v2.0.7-draft-2026-09-07`

## 완료된 데이터 번들

`data/scripts/build_integrated_catalog_bundle.py`가
`data/normalized/v2_0_6_exercise_catalog.csv`를 기준으로 카탈로그를 생성하고 다음 데이터를
하나의 `backend_bundle`에 함께 넣는다.

| 데이터 | 수량/검증 |
|---|---:|
| 통합 운동 카탈로그 | 237건 |
| MET | 카탈로그 각 행에 6개 provenance 필드 |
| 헬스장 무게 제안 | 67건, DOMAIN_APPROVED |
| 집 생활도구 대체·무게 제안 | 34건, DOMAIN_APPROVED |
| 집 운동 변형 후보 | home bundle에 포함 |
| 안전·처방·미디어·대체 관계 | catalog generator 산출물을 그대로 포함 |

생성기는 모든 부가 행의 `exercise_stable_code`가 카탈로그에 존재하는지, 중복·검수 상태·파일
해시·JSONL 건수를 확인한 뒤에만 출력한다. 산출물은
`data/generated/integrated-catalog-v2.0.7-draft/backend_bundle/`와
`data/reports/integrated_catalog_v2_0_7/`에 생성된다.

## 백엔드 인계

담당 영역: `backend/app/modules/catalog/**`, `backend/app/db/**`, importer/migration.

1. 통합 번들의 `catalog/catalog/exercises.jsonl`을 기준으로 237개 운동을 적재하고, MET 6개
   필드(`met_value`, `met_source_code`, `met_source_activity_code`,
   `met_mapping_method_code`, `met_review_status_code`, `met_policy_version`)를 nullable
   컬럼으로 보존한다. 기존 final 번들을 덮어쓰지 말고 새 catalog version으로 등록한다.
2. `body_focus_code`를 catalog repository의 exercise list/detail record에 포함하고,
   `ExerciseListItem`과 `ExerciseDetailResponse`에 optional 호환 필드로 노출한다. 값은
   `BodyFocusCode` enum과 `data/normalized/body_focus_codes_v2.md`의 코드만 허용한다.
3. `primary_body_area_codes`는 주·부위 배열로 계속 제공한다. `body_focus_code`를 배열에서
   추론하거나 프론트에서 재계산하지 말고 카탈로그의 단일 대표 초점을 사용한다.
4. home bundle의 생활도구 가이드는 advisory 데이터로 연결하고, 안전 규칙·운동 장소·통합
   카탈로그의 승인 상태를 우회하지 않는다. gym 무게 제안도 운동 상세의 장비 안내로 제공한다.
5. importer 후속 테스트: 237 stable code 완전 일치, MET 6필드 저장, gym/home 참조 무결성,
   미승인 행 거부, 기존 API 응답 필드 하위 호환.
6. FITT 후속 연결: `data/normalized/catalog_enrichment_v3_fitt.csv`와 승인된 FITT 참조
   데이터의 `frequency`, `intensity`, `time`, `type` 값을 운동 stable code와 함께 적재한다.
   현재 처방 프로필이 참조값만 소비하는 경계를 확장해, Training/Recovery/Feasibility agent가
   proposal을 만들 때 해당 운동의 FITT 참조값과 `source_code`, `policy_version`,
   `review_status_code`를 직접 조회하도록 agent context adapter를 둔다. 미승인·누락 값은
   추론하거나 보간하지 않고 `REVIEW_REQUIRED`로 전달하며, FITT가 안전 veto를 우회하지
   못하도록 최종 integrity validator에서 시간·강도 상한을 재확인한다.
7. 사용자 수준별 FITT 범위는 백엔드에서 먼저 결정한다. 최소 계약은 다음과 같다.

   | 사용자 수준 | 운동 유형 | 세트 | 반복 |
   |---|---|---:|---:|
   | `BEGINNER` | 복합 근력 | 2~3 | 8~12 |
   | `BEGINNER` | 고립 근력 | 2~3 | 10~15 |
   | `INTERMEDIATE` | 복합 근력 | 2~4 | 8~12 |
   | `INTERMEDIATE` | 고립 근력 | 2~4 | 10~15 |

   운동별 저장값은 `min_sets`, `max_sets`, `min_reps`, `max_reps`, `default_sets`,
   `default_reps`를 함께 유지한다. `default_*`는 초기·결정적 fallback 값이고, `max_*`는
   선택 가능한 상한이다. 사용자 수준, 운동 패턴, FITT 승인 상태가 없는 경우 임의로
   범위를 만들거나 상한을 높이지 않는다.
8. 위 범위를 Training agent 프롬프트의 구조화 context로 전달한다. 프롬프트에는 다음 원칙을
   포함한다.

   ```text
   사용자 수준과 운동별 FITT 허용 범위 안에서
   운동 목표, 요청 운동시간, 피로도를 고려하여 세트와 반복수를 결정한다.
   항상 최대값을 사용하지 않는다.
   짧은 운동시간이나 높은 피로도에서는 하한에 가깝게,
   충분한 운동시간과 정상적인 회복 상태에서는 필요한 운동에 한해 상한에 가깝게 설정한다.
   ```

   `4세트×15회` 같은 값을 프롬프트에 고정하지 않는다. AI는 전달된 범위 안에서만 선택하며,
   프롬프트 지시가 검증 규칙을 대체하지 않는다.
9. `RecoveryCeiling`과 compiled-plan integrity validation의 `maximum_sets_per_exercise`,
   `maximum_repetitions_per_set`을 동일한 운동별 FITT 상한에서 계산한다. AI가 상한을
   초과하면 거부·수정하고, coordinator가 상한을 다시 올릴 수 없도록 한다. 상한을 4세트·
   15회로 확장할 때는 관련 golden/safety validation을 함께 갱신한다.
10. deterministic fallback은 `maximum_*`를 그대로 처방값으로 사용하지 않는다. fallback은
    운동별 `default_sets/default_reps`를 사용하고, 해당 default가 현재 사용자 수준·안전
    envelope 안에 있는지 검증한다. default가 없거나 범위를 벗어나면 안전한 보수값 또는
    `REVIEW_REQUIRED`로 실패 안전 처리한다.

## 프론트엔드 인계

담당 영역: `frontend/src/api/types.ts`, catalog/workout 화면과 label mapping.

1. API 타입에 `body_focus_code?: BodyFocusCode | null`를 추가하고, `bodyFocusLabel`로 한글
   주요 근육명을 표시한다. 알 수 없는 코드는 원문을 노출하지 말고 기존 fallback label을
   사용한다.
2. 운동 목록 카드와 상세 화면에서 `body_focus_code`를 주요 근육 한 줄로 표시한다.
   `primary_body_area_codes`는 보조적인 상세 부위 정보로 유지한다.
3. 상세 화면의 장비 안내는 gym starting guide와 home household guide를 구분해 표시한다.
   운동 장소와 사용 가능한 장비에 맞는 안내만 노출하며, 무게 제안은 참고값으로 표시한다.
4. 로딩·빈 값·오류 상태에서 `body_focus_code`와 가이드가 없어도 기존 운동 상세가 렌더링되어야
   한다.
5. 컴포넌트 테스트와 production build에서 대표 초점 표시, gym/home 안내, 누락 데이터 fallback을
   확인한다.

## FITT 에이전트 계약 인계

FITT는 운동 처방을 자동 확정하는 값이 아니라, 에이전트가 후보 운동의 빈도·강도·시간·유형을
일관되게 비교하기 위한 승인 참조 컨텍스트다. 백엔드는 agent 입력 DTO에 `exercise_stable_code`를
키로 한 FITT 참조를 포함하고, 에이전트 출력에는 사용한 `fitt_reference_version`을 남긴다.
프론트엔드는 이 내부 참조값이나 에이전트 컨텍스트를 직접 표시하지 않으며, 최종 루틴의 사용자용
세트·시간 안내만 API 계약에 따라 렌더링한다.

## 실행 및 승격 순서

```text
python data/scripts/build_integrated_catalog_bundle.py
pytest data/scripts/tests/test_build_integrated_catalog_bundle.py
백엔드 importer 검증 → 백엔드/프론트 계약 리뷰 → 새 bundle hash 승인 → 운영 적재
```

현재 작업은 데이터 번들 생성과 인계 문서까지다. DB migration, API 구현, 운영 적재 및
production 승격은 백엔드·프론트엔드 담당자의 별도 승인 작업이다.
