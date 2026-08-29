# v2.0.2 Backend·DB 인계

## 결론

- DB 적재 대상은 `data/generated/exercise-catalog-v2.0.2-final/`의 최종 170건이다.
- 현재 판정은 `READY_FOR_PRODUCTION_IMPORT`이며 `production_eligible=true`다. 주인님의 일괄 승인(`USER_DIRECT_REVIEW_2026_08_29`)을 manifest에 반영했다.
- 201건 Variant 물질화 결과는 `data/generated/exercise-catalog-v2.0.2-intermediate/variant-materialization-v1/`의 검토용 중간 산출물이다. final manifest와 DB 적재 대상에 포함하지 않는다.
- final catalog 구성은 `REPRESENTATIVE` 76건, `VARIANT` 15건, `SEPARATE_EXERCISE` 79건이다.
- DB importer canonical payload는 아래 6개 파일로 고정한다. 나머지 final 산출물은 `final/audit/`로 분리했으며 importer가 directory glob으로 읽지 않는다.

| DB 영역 | canonical payload |
|---|---|
| Exercise catalog | `catalog/exercises.jsonl` |
| Safety | `runtime/safety_rules.jsonl` |
| FITT/Prescription | `prescriptions/prescription_profiles.jsonl` |
| Goal | `prescriptions/goal_tag_links.jsonl` |
| Alternative | `alternatives/resolved_discomfort_alternative_map_v2_0_2.jsonl` |
| Media | `media/media_assets_v2_0_2.csv` |

## 확정 데이터 계약

- 기본 루틴 후보는 final catalog에서 `general_pool_included=true`인 행만 사용한다.
- `PAIN_AREA_NO_LOAD_SAFE_VARIANT` 75건은 독립 수행 가능한 `SEPARATE_EXERCISE`다. `alternative_only=false`, `general_pool_included=true`로 적재한다.
- safe Variant catalog row에는 `pain_discomfort_area_code`와 `condition_codes`를 저장하지 않는다. 통증 부위와 `NRS_1_3`/`NRS_4_6` 조건은 `exercise_alternatives` 관계에만 저장한다.
- 통증 조정은 `exercise_alternatives.pain_discomfort_area_code + condition_code`로 조회하고, 대체 후 Safety를 재검사한다. 관계는 방향성이 있다.
- `DOMAIN_APPROVED` 상태와 함께 이번 일괄 승인 범위·승인 시각·근거를 manifest의 `batch_approval`에 보존했다. 행별 사유는 요구하지 않고 외부 전문가 원천 승인과 주인님 최종 육안 검수를 승인 근거로 사용한다.

## 데이터 → DB 매핑

| 데이터 영역 | 적재 매핑 | 현재 계약과의 영향 |
|---|---|---|
| catalog/version | `catalog_versions.version_code=exercise-catalog-v2.0.2-final`, manifest 원문 SHA-256·전체 metadata·170 count 보존. 컨테이너 source track은 `merged` | manifest의 `import_contract.canonical_payloads`만 적재 입력으로 사용하고 `audit/`는 검증·추적용으로만 보존 |
| exercise identity | final의 `stable_code`를 catalog-version 범위 unique key로 사용하고 DB 내부 UUID `exercises.id`를 FK 기준으로 생성. `exercise_id`/`source_record_id`는 source identity metadata로 보존 | 현재 DB에는 final의 외부 `exercise_id` 필드가 별도 typed column으로 정의되지 않음. stable_code 해석 규칙을 importer에서 고정하고 임의로 UUID를 source ID로 사용하지 않음 |
| source/provenance | `source_track`, `source_identity`, `source_key`, `source_provenance_status`, source URL/license/retrieval metadata를 원문대로 보존 | DATA_MODEL의 `source_track_code` 허용값은 `wger/kspo/gymvisual`인데 final에는 `pain_alternative_policy` 75건도 존재한다. 별도 migration 또는 metadata 보존 방식을 백엔드가 승인해야 하며 `merged`로 덮어 provenance를 잃지 않음 |
| record/family | `record_type`, `family_code`는 stable code와 함께 보존. `REPRESENTATIVE`는 parent 없음, `VARIANT` 15건은 `representative_exercise_id`를 parent stable code로 해석 | 현재 `exercises` 논리 모델에 `record_type`/`family_code`/variant parent typed column이 없다. additive migration 필요 여부만 남기며, 승인 전 JSONB·임의 컬럼 매핑을 확정하지 않음 |
| variant relation | `VARIANT`의 family/parent 관계와 `variant_relation_code/status`를 별도 relation 또는 승인된 metadata로 보존 | 15건 일괄 승인 완료. 추천 풀 사용 가능 |
| pain alternative | source/target을 `exercises.id` FK로 해석하고 `reason_code=DISCOMFORT`, `pain_discomfort_area_code`, `condition_code`, `service_action_code`, `target_strategy_code`, direction·source metadata를 적재 | 현재 nullable selector는 migration `0028_discomfort_alt_conditions` 대상이다. migration 적용·승인은 백엔드 범위이며 이 문서는 요구사항만 인계함 |
| alias/deletion | `alias_migration_v2_0_2.jsonl`은 old stable code → current stable code mapping, `canonical_deletions_v2_0_2.jsonl`은 retired mapping으로 보존. final registry의 retired stable code count는 57 | v2.0.1 catalog/루틴은 삭제하지 않고 `DEPRECATED`로 유지한다. alias/deletion mapping을 hard delete로 처리하지 않음 |
| safety/FITT/goal | stable code를 FK 해석 키로 사용해 `exercise_safety_rules`, `exercise_prescription_profiles`, `exercise_goal_tag_links`에 적재. 각 artifact manifest/hash/count를 transaction 입력으로 검증 | 독립 record의 값은 자동 승인하지 않음. 누락·hash/count 불일치 시 전체 transaction을 fail-closed |
| media | `exercise_media_assets`에 catalog record별 1행. source origin/track/identity/match method는 source metadata에 보존하고 `AVAILABLE + APPROVED`만 노출 | 170행 rights 승인 완료. Gymvisual 원천 ID 87개에 대해 `source_image_s3_key=images/{source_id}-{token}.jpg`, `source_gif_s3_key=videos/{source_id}-{token}.gif`를 로컬 media 파일명에서 매핑했다. S3 canonical alias 업로드 전이므로 기존 `s3_key`·공개 상태는 유지한다. 최종 catalog 밖의 로컬 Gymvisual 19쌍은 적재하지 않는다. |

## 산출물 무결성 기준

| artifact | records | SHA-256 |
|---|---:|---|
| `catalog/exercises.jsonl` | 170 | `121770bfe10451330be2a4ec5921fff6eb861b6dddbfe8f3c9790752705ef053` |
| `runtime/safety_rules.jsonl` | 608 | `036c871f4563135d10d718c29ab7ff276ce0cc10373524f15613585545bb9cda` |
| `prescriptions/goal_tag_links.jsonl` | 170 | `9dab814f77cd7e53e8dc3e317d76d37c0aa4e5dc0b2f784da92bd8657cc70fdf` |
| `prescriptions/prescription_profiles.jsonl` | 372 | `99260424bf350d5c1dc6c5abaf44ab315173c80907f3adf9abc9e7e5b8516503` |
| `alternatives/resolved_discomfort_alternative_map_v2_0_2.jsonl` | 1,104 | `9f55a4e454e23dd4dbf9a6ee67b0ac0b262dc013a13150fa87f9549b45bfc487` |
| `media/media_assets_v2_0_2.csv` | 170 | `9a69bef138c2a619f421738e703012f00a0825cc559e1410e882097cdee44a57` |

모든 FK 집합은 final 170 stable code 집합과 일치하고 orphan은 0건이다. final `manifest.json`에는 `variant_materialization` key가 없으며 final manifest의 catalog count는 170이다. manifest의 hash 목록은 canonical 6개와 audit 24개를 구분한다.

## 시간 정책

- DB CHECK: `abs(estimated_duration_seconds - requested_duration_minutes * 60) <= 300`
- 백엔드는 요청 시간을 임의로 변경하지 않고 ±300초 범위에서 가장 가까운 계획만 선택한다. 차이가 301초 이상이면 실패한다.
- 반복 기반 수행 시간에는 초기 15% 여유를 적용한다. 산식은 `sets * reps * seconds_per_rep * 1.15`이며, 반올림 규칙은 별도 버전으로 고정한다.
- 세트·반복·휴식의 catalog/FITT 원값은 수정하지 않는다. `2~3세트`, `8~12회`와 같은 후보 범위가 있으면 백엔드가 선택한 하나의 구체적인 `sets`·`reps` 값을 계산에 사용한다.
- 휴식시간은 `rest_seconds_per_set` 처방값을 그대로 사용한다. 운동 간 전환은 `default_transition_seconds` 또는 승인된 runtime 전환값을 사용하며 최대 20초를 넘지 않는다.
- `timing_mode_code=REPS`는 위 15% 여유 산식을 적용하고, `timing_mode_code=DURATION`은 catalog의 `work_seconds_per_set`을 임의 확대하지 않는다.
- 준비시간은 실제 `setup_seconds`만 반영하고, 요청 시간에 맞추기 위한 허위 padding은 금지한다. 결과적으로 요청 시간에 맞지 않으면 운동 개수를 줄여 가장 가까운 계획을 선택한다.
- `duration_policy_version`, `pace_profile_code`(초기값 `RELAXED`), `target_delta_seconds`, `rounding/composition rule version`을 decision/routine 저장 정보에 남겨 재현성을 보장한다.

### 시간 정책 DB 저장 계약

- `requested_duration_minutes`는 사용자 요청값을 보존하며 백엔드가 임의로 변경하지 않는다.
- `estimated_duration_seconds`는 setup + warmup + 운동별 수행시간(반복 15% 여유 포함) + 휴식 + 전환 + cooldown의 합계다.
- `target_delta_seconds = estimated_duration_seconds - requested_duration_minutes * 60`로 저장하고, 절댓값이 300초를 초과하면 적재·응답을 실패시킨다.
- `routine_days` 또는 `routines`에는 최소 `duration_policy_version`을 저장한다. `pace_profile_code`, `target_delta_seconds` 및 선택적 운동별 `estimated_item_seconds` snapshot 저장은 재현성 확보를 위해 권장한다.
- 현재 backend routine schema의 exact-duration CHECK와 새 ±300초 정책은 충돌하므로 Alembic migration과 기존 exact-duration 테스트 갱신이 필요하다. migration 적용 전에는 새 정책을 production contract로 활성화하지 않는다.

### FITT 선택 예시

- `3세트 × 10회`, `seconds_per_rep=3`이면 반복 수행시간은 `3 * 10 * 3 * 1.15 = 103.5초`이며 구현의 반올림 규칙에 따라 정수 초로 저장한다.
- 세트 간 휴식 60초와 운동 간 전환 20초는 위 수행시간과 별도로 더한다.
- 실제 계획은 이 운동 하나를 반드시 유지하는 것이 아니라 전체 목표·Safety·phase 조건을 만족하는 후보 중 요청 시간과 가장 가까운 조합을 선택한다.

## production blocker 처리 결과

- blocker 5건 모두 해소 처리했다. `production_blockers_v2_0_2.json`의 `blocker_count=0`, `status=APPROVED`다.
- Variant 15건, 난이도 변경 29건, Alternative 1,104건은 `USER_DIRECT_REVIEW_2026_08_29` 일괄 승인으로 반영했다.
- Media/Rights 102건은 권리 검수 완료로 `APPROVED` 처리했으며, 실제 media asset이 없는 행은 `UNAVAILABLE`·`HIDDEN`으로 유지했다.
- final manifest는 `PRODUCTION_APPROVED`, `production_eligible=true`다. final catalog는 170건이며 중간 201건은 계속 제외한다.

## 백엔드 구현 요청

1. final manifest·각 JSONL/CSV의 hash, byte count, record count, stable code FK를 Pydantic/importer에서 먼저 검증한다.
2. catalog, lookup, exercise, body-part/equipment/location, goal/FITT, safety, alternative, media를 하나의 staging transaction으로 적재한다. 부분 성공을 남기지 않는다.
3. 기본 후보·통증 대체 조회 규칙은 위 확정 계약을 사용하고, 대체 후 독립 Safety veto를 재검사한다.
4. v2.0.1은 삭제하지 않고 `DEPRECATED`로 유지한다. v2.0.2 final activation은 이번 일괄 승인과 readiness 결과를 기준으로 진행한다.
5. FITT 원값을 변경하지 않고 위 시간 조성 산식, `RELAXED` pace profile, ±300초 closest-plan 선택, 301초 초과 fail-closed를 모든 routine/decision 경로에 동일하게 적용한다.
6. `duration_policy_version`, `pace_profile_code`, `target_delta_seconds`, 선택적 `estimated_item_seconds` snapshot의 저장 위치와 nullable/backfill 전략을 migration에서 확정한다.
7. 현재 `build_v2_backend_bundle.py`는 기본값이 v2.0.1이며 final 170 bundle의 검증기로 사용하지 않는다. v2.0.2 six-payload importer/bundle 경로와 migration 필요 사항은 백엔드가 승인해 확정한다.

## API/schema 영향

이번 작업에서 API·backend model·migration·`docs/DATA_MODEL.md`는 수정하지 않았다. 위 매핑 중 `source_track=pain_alternative_policy`, `record_type`, `family_code`, variant parent, catalog-level provenance 및 nullable Alternative selector는 현재 모델과의 호환성 검토/ migration 후보로만 인계한다.

## 보안·개인정보 및 제한

- 사용자 식별자·원시 건강 데이터·토큰은 생성 산출물에 포함하지 않았다.
- 통증 부위/조건은 운동 catalog identity와 분리해 관계에만 둔다. safety 승인 전에는 추천 경로에서 사용하지 않는다.
- 권리 증적은 참조값만 보존하고 원문 비밀정보는 저장하지 않는다.
- 170건 중 68건만 실제 media를 노출하고, 102건은 `UNAVAILABLE`·`HIDDEN`으로 제공한다. media binary 업로드는 별도 작업이다.
