# v2.0.2 Variant 독립 운동 레코드 반영 결과

- 생성 시각: `2026-08-28T00:00:00+09:00`
- 상태: `DRAFT_VARIANTS_MATERIALIZED_REVIEW_REQUIRED`
- 운영 적격: `false`

## 집계

| 항목 | 건수 |
|---|---:|
| 대표운동 | 101 |
| PRIMARY_VARIANT 독립 row | 66 |
| SECONDARY_VARIANT 독립 row | 4 |
| 별도 운동 | 30 |
| Variant 독립 row 합계 | 70 |
| 최종 통합 카탈로그 전체 운동 | 201 |
| REVIEW_REQUIRED 관계 | 80 |
| 미물질화 REVIEW_REQUIRED canonical pair | 10 |

## 처리 원칙

- 방향이 있는 alias-to-representative Variant 69건과 명시된 REX-000105 1건은 독립 `VARIANT` row로 물질화했다.
- 관계 후보 집계는 PRIMARY 75건·SECONDARY 5건을 보존한다. 이 중 canonical-canonical 10건은 대표 방향이 확정되지 않아 row를 만들지 않았다.
- 모든 Variant의 관계·안전·FITT 상태는 `REVIEW_REQUIRED`이며 `production_eligible=false`다.
- `ROPE`·`SUSPENSION_STRAPS`는 승인된 장비 코드 정책에 따라 `STRETCH_STRAP`으로 정규화했고, `BENCH`·`CHAIR`는 장비 코드에서 제외했다.
- HOME 허용 장비를 사용하는 row의 location_codes는 `HOME`,`GYM`으로 정규화하고, HOME 미지원 장비 row는 `GYM`만 유지한다.

## 산출물

- `generated/exercise-catalog-v2.0.2-final/catalog/exercises.jsonl`
- `generated/exercise-catalog-v2.0.2-final/variant_relationship_review_v2_0_2.jsonl`
- `generated/exercise-catalog-v2.0.2-final/family_representative_mapping_v2_0_2.jsonl`
- `generated/exercise-catalog-v2.0.2-final/variant_safety_fitt_mapping_v2_0_2.jsonl`
- `generated/exercise-catalog-v2.0.2-final/variant_integrity_report_v2_0_2.json`
