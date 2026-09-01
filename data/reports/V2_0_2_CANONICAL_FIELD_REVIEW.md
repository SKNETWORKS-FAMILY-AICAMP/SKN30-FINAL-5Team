# v2.0.2 canonical 운동 필드·대표운동 검수 보고서

- 검수 버전: `v2.0.2-canonical-field-review-v1.1.0`
- 생성 시각: `2026-08-28T00:00:00+09:00`
- 입력: 관계 중복 정리가 완료된 v2.0.2 canonical 집합
- 운영 사용: `production_eligible=false` 유지

## 결과

- 대표운동 수: **131**
- 변형운동 후보 수: **1**
- 변형운동 후보 review_required 수: **1**
- 필드 수정 수: **220**
- review_required 수: **131**
- 데이터 review_required 수(라이선스 제외): **31**
- 삭제된 대표운동 수: **4**
- 1차 데이터 검수 행 수: **36**
- 장비-only 확정 후보 수: **1**
- 수정 이력 정합성 오류: **0**
- 애매한 review_required 수: **1**
- 필수 필드 결측: **0**
- 허용되지 않은 taxonomy code: **0**
- 논리 충돌: **9**

## 해석

- 대표운동은 canonical identity별 1건으로 유지했으며 HOME 가능 여부를 이유로 대표운동을 맨몸 운동으로 교체하지 않았다.
- 장소별 기본 추천 가능 여부는 대표성 판단과 분리해 identity review 산출물의 `home_default_recommendation`·`gym_default_recommendation`으로 기록했다.
- `BENCH`·`CHAIR`는 v2 release equipment code에서 제거하고 필요한 지지는 `setup_condition_ko`에 보존했다.
- 주인님이 라이선스 자체는 문제없다고 확인했으므로 라이선스는 추가 검수 대상에서 제외한다. 다만 원천 메타데이터의 기존 review flag는 감사 추적을 위해 그대로 보존했고, 데이터 검수 수치는 해당 라이선스 flag를 제외해 별도 계산했다.
- REX-000129는 사용자 요청에 따라 활성 canonical에서 제외했으며, 삭제 이력과 기존 stable code는 migration 산출물에 남겼다.
- 활성 catalog 난이도는 BEGINNER/INTERMEDIATE만 허용한다. REX-000107·116·129·132는 삭제했고, REX-000105는 REX-000006의 케이블·로프 변형 후보로 분리했다.
- REX-000121은 본문 수행 단계에 맞춰 맨몸 bicycle crunch로 canonicalize했지만, 원천 이미지·제목의 band 표기는 provenance와 review flag로 보존했다.
- 장비-only 표는 동일 수행으로 확정할 수 있는 후보와, 자세·지지·부하 전달이 달라 확정하지 않은 근접 후보를 구분한다.

## 산출물

- 정제 canonical: `exercise-catalog-v2.0.2-final/canonical_exercises_v2_0_2_refined.csv` / `.jsonl`
- field correction: `exercise-catalog-v2.0.2-final/field_corrections_v2_0_2.csv` / `.jsonl`
- representative identity review: `exercise-catalog-v2.0.2-final/representative_identity_review_v2_0_2.csv` / `.jsonl`
- 대표운동 변형 후보: `exercise-catalog-v2.0.2-final/representative_variant_candidates_v2_0_2.csv` / `.jsonl`
- alias/migration: `exercise-catalog-v2.0.2-final/alias_migration_v2_0_2.csv` / `.jsonl`
- 1차 데이터 검수: `exercise-catalog-v2.0.2-final/canonical_data_first_pass_review_v2_0_2.csv` / `.jsonl`
- 장비-only 후보: `exercise-catalog-v2.0.2-final/equipment_only_same_method_review_v2_0_2.csv` / `.jsonl`
- 삭제 이력: `exercise-catalog-v2.0.2-final/canonical_deletions_v2_0_2.csv` / `.jsonl`
- validation JSON: `exercise-catalog-v2.0.2-final/canonical_field_validation_report_v2_0_2.json`
