# Normalized data

출처별 표현을 공통 exercise/FITT/safety schema로 정규화한 중간 결과를 둡니다. 프로덕션 승인 상태와는 구분합니다.

## v2.0.6 운동 카탈로그 기준 파일

`v2_0_6_exercise_catalog.csv`가 v2.0.6 통합 운동 카탈로그의 유일한 사람 수정 기준 파일입니다.
필수 컬럼과 정규화 컬럼을 이 파일에서 수정하고,
`data/scripts/build_v2_0_6_catalog_from_normalized.py`로
`data/generated/exercise-catalog-v2.0.6-draft/review_catalog/` 아래의 JSON·CSV·매핑·빈값
리포트를 재생성합니다. raw JSON·review batch·generated 산출물은 직접 수정하지 않습니다.

MET 6개 컬럼은 `data/scripts/enrich_v2_0_6_met.py`가 지정된
`data/raw/physical_activity_guidelines/adult_compendium_mvp_reference_subset.jsonl`의
직접 대응을 먼저 확인한 뒤 운동 형태·장비·자세·수행 방식이 충분히 대응하는 activity를
`SIMILAR_ACTIVITY`로 매핑합니다. `met_value`는 지정 JSONL activity의 값을 그대로 사용하고
계산·평균·보간·운동 간 복사는 하지 않습니다. 조건이 충분히 대응하지 않는 행은 `met_value`와
activity provenance를 빈값으로 남깁니다. 검수 전에는 `met_review_status_code`를
`REVIEW_REQUIRED`로 두며, 이번 승인 후 기준 CSV의 매핑 237건은
`DOMAIN_APPROVED`로 기록합니다. 승인 근거는
`data/reports/v2_0_6_met/met_review_approval_manifest.json`에 고정하지만 production
승인으로 해석하지 않습니다. `rank`와
`variant_difficulty_rank`는 생성하지 않습니다.

최초 생성 또는 원천 결과 재수집이 필요한 경우에만
`data/scripts/bootstrap_v2_0_6_normalized_catalog.py`를 사용합니다.

기준 CSV가 최신 검토 산출물보다 뒤처진 경우에는
`data/scripts/merge_v2_0_6_recent_into_normalized.py`로 최신
`review_catalog/exercise_catalog_merged_draft.json` 240개를 병합합니다. `stable_code` 중복은
최신 행이 대체하고, MET 6개 컬럼은 `met_provenance.csv`의 같은 `stable_code` 행이
대체합니다. 이 스크립트는 지정된 Adult Compendium JSONL의 activity code, source id,
MET 값까지 확인한 뒤 기준 CSV를 다시 쓰며, 불일치 시 실패합니다. 병합 후에는
`build_v2_0_6_catalog_from_normalized.py`와 draft bundle 생성기를 재실행합니다.

검수 배치의 완료된 `body_focus_code`를 기준 CSV에 반영할 때는
`data/scripts/apply_v2_0_6_body_focus_review_to_normalized.py`를 사용합니다. 이 단계는
`body_focus_code`만 변경하며, taxonomy에 없는 값은 빈값으로 보류합니다. 다른 빈 컬럼의
권장 입력 원천·검수 단계는 `data/reports/v2_0_6_catalog_merge/blank_field_recommendations.json`
에서 확인합니다. `training_type_code`는 같은 검수 배치와 문서화된 매핑 규칙을 사용해
`data/scripts/apply_v2_0_6_training_type_to_normalized.py`로 별도 반영하며, body focus가
미확정인 세 행은 명시된 `STRENGTH` 검수값이 있을 때만 `STRENGTH`로 채웁니다.

국민체력100 원천의 초기 필드 매핑과 금지 규칙은
[KSPO_FITNESS100_MAPPING_PROPOSAL.md](KSPO_FITNESS100_MAPPING_PROPOSAL.md)를 따른다. 이 문서는 DRAFT
제안이며 공통 enum과 외부 도메인 검토 전 normalized seed를 만들지 않는다.

헬스장 운동 보강 범위와 wger 원천의 매핑 경계는
[GYM_EXERCISE_SOURCE_COVERAGE.md](GYM_EXERCISE_SOURCE_COVERAGE.md)를 따른다. 원천의 이름
일치는 정규화 운동의 동일성, 초보자 적합성 또는 안전 승인을 의미하지 않는다.

`physical_activity_reference_v0.1.0/`은 WHO·CDC·질병관리청의 일반 성인 주간 권고,
CDC 강도 경계, 2024 Adult Compendium의 MVP 관련 부분집합을 분리해 보존한 DRAFT다.
애플리케이션 스키마와 개별 운동 MET 매핑은 미확정이며 운영 적재 대상이 아니다.
