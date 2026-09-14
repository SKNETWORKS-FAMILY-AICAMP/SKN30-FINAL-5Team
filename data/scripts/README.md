# Data scripts

## v2.0.6 통합 카탈로그 단일 기준 파일

사람이 수정할 v2.0.6 카탈로그 기준 파일은 오직
`data/normalized/v2_0_6_exercise_catalog.csv`다. 필수 컬럼과 기존 catalog 컬럼을 모두
가지며, 배열은 `|`로 연결한다. raw JSON, additions JSON, 검수 batch CSV, generated JSON·CSV는
이 기준 파일을 초기화하거나 출력하는 보조 산출물이며 이후 직접 수정하지 않는다.

최초 1회만 현재 draft를 단일 기준 파일로 초기화한다. 이 단계에서 기존 원천 매핑과
`v2_0_6_training_body_focus_review.csv`의 신규 `stable_code`·`name_ko` 결과를 보존한다.

```bash
python3 data/scripts/bootstrap_v2_0_6_normalized_catalog.py
```

그 다음부터는 정규화 CSV만 수정하고 아래 한 명령으로 JSON·전체 검수 CSV·매핑·빈값·중복
리포트를 생성한다. 이 최종 생성기는 raw, additions, review CSV를 읽지 않는다.

```bash
python3 data/scripts/build_v2_0_6_catalog_from_normalized.py
```

생성 결과는 `data/generated/exercise-catalog-v2.0.6-draft/review_catalog/` 아래의
`exercise_catalog_merged_draft.json`, `exercise_catalog_merged_draft.csv`와
`exercise_catalog_*_report.json`이며 모두 `DRAFT`·`production_eligible=false`다.

### v2.0.6 MET 매핑

MET 보강은 지정된
`data/raw/physical_activity_guidelines/adult_compendium_mvp_reference_subset.jsonl`만
신규 MET 원천으로 사용한다. 먼저 직접 대응을 확인하고, 운동 형태·장비·자세·수행 방식이
충분히 대응하는 activity는 `SIMILAR_ACTIVITY`로 매핑한다. `met_value`는 해당 JSONL activity에
실제 존재하는 숫자만 그대로 사용하며 계산·평균·보간·운동 간 복사는 하지 않는다. 속도·경사·
사이클처럼 조건이 충분히 대응하지 않는 행은 빈 MET 값과 `REVIEW_REQUIRED` 상태로 남긴다.
검수 승인 시에는 `met_review_approval_manifest.json`의 source hash와 승인 범위를 검증한
뒤 `DOMAIN_APPROVED`로 기록한다. 이 승인은 MET 필드에만 적용되며 카탈로그·Safety·
대체관계·미디어의 승인을 의미하지 않는다.

```bash
python3 data/scripts/enrich_v2_0_6_met.py --force
python3 data/scripts/build_v2_0_6_catalog_from_normalized.py
```

승인된 MET를 재생성할 때:

```bash
python3 data/scripts/enrich_v2_0_6_met.py --force \
  --review-status-code DOMAIN_APPROVED \
  --approval-manifest data/reports/v2_0_6_met/met_review_approval_manifest.json
python3 data/scripts/build_v2_0_6_catalog_from_normalized.py \
  --met-approval-manifest data/reports/v2_0_6_met/met_review_approval_manifest.json
```

결과는 기준 CSV의 MET 6개 컬럼과 `data/reports/v2_0_6_met/` 아래의 전체 매핑 근거·DIRECT
목록·SIMILAR_ACTIVITY 목록·미매핑·provenance·컬럼 출처·rank 미사용 리포트다. 사람 검수 전
모든 결과는 DRAFT이며 `production_eligible=false`다.

### v2.0.6 backend projection (237행)

DB 적재용 파생 번들은 정규화 CSV 237행과 승인된 미디어 파일명을 exact source identity로
투영한다. `recovery_eligible` 빈값은 승인된
`v2_representative_decisions.json`의 training type 정책으로만 보완하고,
`general_pool_included` 빈값은 `null`로 보존한다. 생활도구 대체·주의사항·대체운동 보조자료는
장비 설명이나 `alternatives`에 복사하지 않고 입력에서 제외한다. 단, 백엔드 importer가 요구하는
stretch-strap → bodyweight fallback 1건만 별도 승인 manifest에서 읽는다.

```bash
UV_CACHE_DIR=/private/tmp/skn30-uv-cache uv run python data/scripts/build_v2_0_6_backend_bundle.py
UV_CACHE_DIR=/private/tmp/skn30-uv-cache uv run python data/scripts/validate_v2_backend_bundle.py \
  data/generated/exercise-catalog-v2.0.6-final/backend_bundle
```

생성 번들은 237개 catalog/media, 1개 fallback 관계를 포함하지만 import 전까지는
`DRAFT`·`production_eligible=false`다. 운영 적재는 승인 registry와 exact hash/count를
검증하는 v2.0.6 전용 promotion 스크립트로 수행하고, 활성화 시에만
`production_eligible=true`로 전환한다.

```bash
UV_CACHE_DIR=/private/tmp/skn30-uv-cache uv run python -m backend.scripts.catalog_promote_v2_0_6
UV_CACHE_DIR=/private/tmp/skn30-uv-cache uv run python -m backend.scripts.catalog_promote_v2_0_6 --activate
```

완료된 training/body focus 검수값을 기준 CSV에 반영하려면 다음을 실행한다. 정확한
`source_identity`로 조인하며 `body_focus_code`만 변경하고, 기존 허용 taxonomy와 충돌하는
값은 빈값으로 보류한다.

```bash
python3 data/scripts/apply_v2_0_6_body_focus_review_to_normalized.py
python3 data/scripts/apply_v2_0_6_training_type_to_normalized.py
python3 data/scripts/build_v2_0_6_catalog_from_normalized.py
python3 data/scripts/recommend_v2_0_6_blank_fields.py
```

빈 컬럼별 권장안은 `data/reports/v2_0_6_catalog_merge/blank_field_recommendations.json`
및 CSV에서 확인한다. 권장안은 자동 승인이나 자동 추론을 의미하지 않는다.

### 생활도구 보조자료 검수와 적재 제외

생활도구 대체 제안·주의사항·대체운동 후보는 검수 후 각 JSONL의
`review_status_code=DOMAIN_APPROVED`로 기록하고, 다음 검증기로 구조·stable_code·장비·
난이도·부위 일치 여부를 다시 확인한다.

```bash
python3 data/scripts/validate_home_equipment_substitution_guides.py
```

이 자료들은 v2.0.6 최종 카탈로그의 장비 설명이나 `alternatives`에 복사하지 않는다.
검수 JSONL, gap report, validation report는 증적으로만 보존하며 DB 적재 입력에서는
제외한다. v2.0.6의 카탈로그 입력은 `data/normalized/v2_0_6_exercise_catalog.csv`
하나다.

기존 `merge_v2_0_6_catalog_additions.py`는 원천·기존 draft를 단일 기준 파일로 옮기는
일회성 bootstrap/이력 재현용으로만 사용한다. 최종 생성에 다시 사용하지 않는다.

```bash
python3 data/scripts/merge_v2_0_6_catalog_additions.py \
  --catalog data/generated/exercise-catalog-v2.0.6-draft/backend_bundle/catalog/exercises.jsonl \
  --additions data/generated/exercise-catalog-v2.0.6-draft/backend_bundle/catalog/exercise_catalog_additions.json \
  --output data/generated/exercise-catalog-v2.0.6-draft/backend_bundle/catalog/exercise_catalog_merged_draft.json \
  --report-dir data/generated/exercise-catalog-v2.0.6-draft/backend_bundle/catalog
```

같은 입력·경로로 다시 실행하면 DRAFT와 audit 산출물의 byte/hash가 동일해야 한다.
`exercise_catalog_merge_report.json`, `exercise_catalog_duplicate_review.json`,
`exercise_catalog_unmapped_fields.json`, `exercise_catalog_source_mapping.json`,
`exercise_catalog_source_gap_report.json`은 병합·충돌·원천 매핑·원천 부재 컬럼을 기록한다.
원천 초기화 결과의 원천 매핑은 `data/normalized/v2_0_6_catalog_source_mapping.json`에
보존되며, 이후 생성된 값의 출처는 단일 기준 CSV로 기록된다.

## training/body focus 후보 검수 큐

`build_training_body_focus_candidates.py`는 merged catalog 240건을 입력으로 받아
`training_body_focus_candidates.jsonl`을 생성한다. additions는 `id`와
`source_identity`의 정확한 일치로만 연결하고, 기존 Gymvisual 행은 raw 원천의 동일 ID를
사용한다. 산출물은 검수용 후보·근거·충돌만 담으며 merged catalog나 runtime schema를
변경하지 않는다. `CARDIO`, `MOBILITY`, 원천 충돌과 애매한 body focus는
`REVIEW_REQUIRED`로 남긴다.

```bash
python3 data/scripts/build_training_body_focus_candidates.py
```

## v2.0.6 training/body focus 검수 CSV

`build_v2_0_6_training_body_focus_review_csv.py`는 merged catalog JSON과
`training_body_focus_candidates.jsonl`을 exact `source_identity`로 연결해 Excel 검수용
UTF-8 BOM CSV를 생성한다. 원본 `body_focus_code`가 비어 있는 행에만
`body_focus_code_candidate`를 채우고, 기존값은 보존한다. 후보와 기존값이 모두 없으면
빈칸으로 남긴다. 사용자 직접 검수 override는 이 CSV에만 적용하며 원본 JSON과 후보 JSONL은
변경하지 않는다. 배열은 `|`로 연결하고,
정렬·행 수·ID 집합을 검증한다. `training_type_review_status`,
`body_focus_review_status`, `review_note`는 사람 검수 입력란이므로 빈칸으로 출력한다.
`training_type_code`는 유효한 `body_focus_code`에서 파생한다. `CARDIO`는 `CARDIO`,
`MOBILITY`는 `MOBILITY`, 그 외 부위 코드는 `STRENGTH`로 채우며 body focus가 없으면 빈칸으로
남긴다.

```bash
python3 data/scripts/build_v2_0_6_training_body_focus_review_csv.py
```

CSV의 유효 body focus로 merged draft JSON의 빈 `training_type_code`를 채울 때는 다음
스크립트를 사용한다. 기존 값과 파생 결과가 충돌하면 실패하며, body focus가 없는 행은
추정하지 않는다.

```bash
python3 data/scripts/apply_v2_0_6_training_type_from_body_focus.py
```

검수 CSV의 `body_focus_code`를 merged draft JSON에 반영할 때는 다음 스크립트를 사용한다.
빈 CSV 값은 JSON의 기존값을 유지하며, runtime `exercises.jsonl`은 변경하지 않는다.

```bash
python3 data/scripts/apply_v2_0_6_training_body_focus_review_to_catalog.py
```

## 통합 운동 카탈로그 v1 (단일 작업표)

`data/normalized/catalog_enrichment_v2.csv`는 원천 메타데이터 작업표이고,
`data/normalized/catalog_enrichment_v3_fitt.csv`는 FITT·영문명까지 반영한 최신 정규화본이다.
최종 생성기는 v3만 읽고, 생성 CSV는 직접 수정하지 않는다.

최초 작업표만 보존 원천과 기존 body-focus 매핑에서 초기화한다. 이미 검토 중인 작업표를 덮어쓸
때는 명시적으로 `--force`를 사용한다.

```bash
python3 data/scripts/bootstrap_catalog_enrichment_v2.py
python3 data/scripts/build_catalog_enrichment_v3_fitt.py
python3 data/scripts/build_fitt_review_log.py
python3 data/scripts/build_exercise_catalog_v1.py
```

생성 결과는 `data/generated/exercise-catalog-v1.0.0/exercise_catalog_v1.csv`다. 모든 필수 상태가
`APPROVED`가 아니면 생성 상태는 `REVIEW_REQUIRED`이며 `READY_FOR_MEDIA` 또는
`DOMAIN_APPROVED`로 승격되지 않는다.

`build_catalog_enrichment_v3_fitt.py`는 패턴별 FITT 템플릿·타이밍·강도를 적용하고, 통합 원천의
`name_en`(없으면 `source_name`)을 v3와 최종 카탈로그까지 보존한다. 검토 로그는 v3의 템플릿과
기본값을 검증한다. FITT 검토 완료본은 v3에서만 `APPROVED`로 반영하며, 다른 미승인 검토 상태는
승격하지 않는다.

버전 표기 원천의 중복 노출 결정도 같은 작업표에서 관리한다. `PRIMARY`는 사용자 노출 기본
운동, `MEDIA_VARIANT`는 동일 동작의 원천 미디어 보존 행, `DISTINCT_VARIANT`는 별도 노출하는
가동범위 변형이다. `canonical_exercise_id`, `variant_relation_code`, `variant_basis`를 함께
기록하며 원천 ID는 삭제하지 않는다.

## 통합 운동 카탈로그 v0.5

Gymvisual·Wger·KSPO 원천을 하나의 영구 ID와 검증 가능한 review catalog로 재생성합니다.
원천 파일은 수정하지 않으며, registry에 없는 source key는 fail-closed로 중단합니다.

```bash
python3 data/scripts/build_integrated_exercise_review.py
python3 data/scripts/validate_integrated_exercise_review.py
python3 data/scripts/build_integrated_catalog_data_dictionary.py
```

최초 registry를 만들거나 새로운 source key를 명시적으로 추가할 때만 bootstrap 명령을
사용합니다. 기존 registry의 ID는 보존됩니다.

```bash
python3 data/scripts/bootstrap_integrated_catalog_registry.py \
  data/validation/review_batches/gymvisual-integrated-review-v0.1.0/integrated_exercise_review.csv
```

생성 결과는 `data/validation/review_batches/gymvisual-integrated-review-v0.1.0/`의 CSV·alias·manifest,
`data/normalized/`의 schema·registry·data dictionary, `data/reports/`의 검증 결과와 사람 검토
목록이다. 검증 결과가 `PASS_WITH_PRODUCTION_BLOCKERS`여도 운영 적격을 뜻하지 않으며,
`production_eligible`은 모든 게이트를 통과하기 전까지 `false`다.

## KSPO Fitness100 1차 검토 배치

검증된 profile의 `MVP_SCOPE_REVIEW` 후보에서 수동 검토 순서 50개를 생성합니다.
이 배치는 최종 쇼트리스트나 승인 카탈로그가 아닙니다. 동일 원천 운동명은 배치 안에서만
원천 메타데이터 누락이 적은 대표 1건을 사용하고, 원천 장소·도구 조합을 순회해 검토
다양성을 확보합니다.

```powershell
python data/scripts/build_kspo_fitness100_review_batch.py build `
  data/validation/profiles/<actual-profile-directory> --size 50
```

생성된 배치는 해시와 상태를 다시 검증할 수 있습니다.

```powershell
python data/scripts/build_kspo_fitness100_review_batch.py verify `
  data/validation/review_batches/<actual-review-batch-directory>
```

모든 행은 `DRAFT_REVIEW_QUEUE`, `DRAFT`, `production_eligible=false`를 유지합니다.
운동 분류, 초보자 적합성, 실행 용량, 자세 문구, 미디어 권리, 안전 및 대체 관계는
자동 판정하지 않습니다.

배치 v0.2부터 검토 결과 입력 열과 `catalog_review_records_template.csv`를 함께 생성합니다.
정규화 ID, 한국어 표시명, taxonomy, 초보자 적합성, 실행 안내·미디어 권리·도메인 안전 상태,
포함 여부는 생성 시 모두 빈 값 또는 `PENDING`입니다. 운동마다 `DATA_OWNER`,
`BACKEND_REVIEWER`, `PM_REVIEWER`, `DOMAIN_REVIEWER` 네 역할의 DRAFT 증적 행이 있습니다.

원본 배치를 직접 승인 데이터로 수정하지 말고 검토용 사본에서 작성한 뒤 검증합니다.

```powershell
python data/scripts/validate_kspo_fitness100_review_results.py `
  "data/validation/review_batches/<training-video-review-batch-v0.2.0>" `
  "<작성한-mapping-results.csv>" `
  "<작성한-evidence-results.csv>"
```

원천 식별자와 원천명 등 불변 필드가 바뀌거나, `INCLUDE`/`MERGE` 행에 필수 검토 상태와
역할별 증적이 없으면 실패합니다. 검증 성공도 프로덕션 승격을 의미하지 않으며 결과의
`production_eligible`은 항상 `false`입니다. 게이트 규칙은
[REVIEW_RESULTS_GATE.md](../validation/REVIEW_RESULTS_GATE.md)를 따릅니다.

v0.1.0 배치는 검토 결과 열이 없으므로 현재 verifier로 검증되지 않습니다. 기록으로만
보존하고 검토는 v0.2.0 배치에서 진행합니다.

재현 가능한 수집·정규화·seed 생성 도구 위치입니다.

## 국민체력100 원문 수집

공공데이터포털에서 데이터셋 `15108846`의 개발계정 활용신청을 한 뒤, 발급된
**Decoding 일반 인증키**를 현재 셸에만 설정합니다. 키를 파일이나 명령행 인자로
전달하지 않습니다.

PowerShell 예시:

```powershell
$env:DATA_GO_KR_SERVICE_KEY = '<decoding-key>'
python data/scripts/kspo_fitness100_pipeline.py collect --endpoint training-video
```

기본 산출물은
`data/raw/kspo_fitness100_video/snapshots/<UTC timestamp>-<endpoint>/`에 생성되며 Git에서
무시됩니다. 원문 JSON 페이지와 해시·출처·라이선스를 기록한 `manifest.json`을
포함합니다. 영상/썸네일 바이너리는 수집하지 않습니다.

수집 결과 재검증:

```powershell
python data/scripts/kspo_fitness100_pipeline.py validate `
  data/raw/kspo_fitness100_video/snapshots/<UTC timestamp>-<endpoint>
```

지원 endpoint는 `training-video`, `standard-fitness`, `routine`입니다.
`musculoskeletal` 데이터는 의료·재활 표현 검토 전 기본 수집 대상에서 제외합니다.

단위 테스트:

```powershell
python -m unittest discover -s data/scripts/tests -v
```

린터와 타입 체커는 루트 `pyproject.toml` 설정을 사용합니다.

```powershell
pip install --group dev
ruff check .
ruff format --check .
mypy
```

이 스크립트는 Python 표준 라이브러리만 사용합니다. ruff와 mypy는 개발 도구이며 실행
의존성이 아닙니다. 수집 결과는 `DRAFT`이며 정규화 또는 프로덕션 seed가 아닙니다.

## 스트레칭·가동성 후보 선정

Gym Visual 원천은 수정하지 않고 선언형 정책을 적용해 mobility 후보 프로파일과 사람 검토
배치를 생성합니다. 이 단계에서는 family/variant 후보만 기록하며 대체 관계나 generated
seed를 만들지 않습니다.

```bash
python3 data/scripts/profile_gymvisual_mobility.py profile
python3 data/scripts/profile_gymvisual_mobility.py verify \
  data/validation/profiles/gymvisual_mobility_profile.json
python3 data/scripts/build_gymvisual_mobility_review.py
```

정책 파일은 `data/normalized/mobility_selection_policy.json`, 프로파일은
`data/validation/profiles/gymvisual_mobility_profile.json`, 검토 배치는
`data/validation/review_batches/gymvisual_mobility_review.csv`에 둡니다. 검토 전 산출물은
모두 `DRAFT_REVIEW_QUEUE` 또는 `PENDING`이며 `production_eligible=false`입니다.

## 원천 profiling과 검토 인벤토리

검증된 snapshot을 입력해 필드 결측·고유값·분포와 `(file_nm, trng_nm)` 단위의
검토 인벤토리를 생성합니다.

```powershell
python data/scripts/profile_kspo_fitness100.py profile `
  data/raw/kspo_fitness100_video/snapshots/<실제-snapshot-directory>
```

생성된 profile을 다시 검증합니다.

```powershell
python data/scripts/profile_kspo_fitness100.py verify `
  data/validation/profiles/<실제-profile-directory>
```

`candidate_review.csv`는 PM·도메인 검토 편의를 위한 목록이며 seed가 아닙니다.
모든 행은 `DRAFT`, `production_eligible=false`이고 안전·난이도·초보자 적합성 검토
필요 코드를 포함합니다.

## wger 헬스장 운동 보강 수집

wger 공개 API의 운동 카탈로그와 장비·분류·근육·언어·라이선스 참조 데이터를 별도
snapshot으로 수집합니다. 공개 조회에는 API 키가 필요하지 않습니다. 운동·번역·미디어의
라이선스가 다를 수 있으므로 항목별 메타데이터를 보존하며 이미지·동영상 파일은
다운로드하지 않습니다.

```powershell
python data/scripts/wger_exercise_pipeline.py collect
```

수집 결과를 다시 검증합니다. PowerShell에서 `<snapshot-path>`를 문자 그대로 입력하지
말고 실제 폴더 경로를 따옴표로 감쌉니다.

```powershell
python data/scripts/wger_exercise_pipeline.py validate `
  "data/raw/wger_exercise_catalog/snapshots/<실제-snapshot-directory>"
```

검증된 snapshot에서 헬스장 장비 또는 목표 운동명 근거가 있는 검토 후보를 생성합니다.

```powershell
python data/scripts/profile_wger_exercises.py profile `
  "data/raw/wger_exercise_catalog/snapshots/<실제-snapshot-directory>"
```

```powershell
python data/scripts/profile_wger_exercises.py verify `
  "data/validation/profiles/<실제-wger-profile-directory>"
```

`gym_candidate_review.csv`는 랫풀다운, 덤벨로우, 케이블로우 등의 원천 이름·장비
커버리지를 검토하기 위한 목록입니다. 텍스트 일치는 정규화 taxonomy 매핑이 아니며,
모든 행은 한국어 명칭·초보자 적합성·실행 용량·안전·라이선스 검토 전까지 `DRAFT`입니다.

## wger 헬스장 핵심 검토 배치

검증된 wger profile에서 목표 운동군 할당량과 원천 분류·장비 다양성을 사용해 60개
검토 순서를 생성합니다. 랫풀다운, 덤벨로우, 시티드 케이블로우의 요청 명칭은 존재할 때
첫 행에 포함합니다. 이 순서는 품질·안전 점수가 아니며 최종 운동 카탈로그가 아닙니다.

```powershell
python data/scripts/build_wger_gym_review_batch.py build `
  "data/validation/profiles/<실제-wger-profile-directory>" --size 60
```

```powershell
python data/scripts/build_wger_gym_review_batch.py verify `
  "data/validation/review_batches/<실제-gym-core-review-directory>"
```

생성된 CSV의 한국어명, 정규화 ID, taxonomy, 초보자 적합성, 실행 안내, 라이선스, 안전,
포함 여부 필드는 모두 미입력 또는 `PENDING`이다. 생성 원본을 직접 승인 데이터로 수정하지
말고 검토용 사본에서 작성한 뒤 별도 승인 증적과 함께 반영한다.

배치 v0.2부터 `catalog_review_records_template.csv`를 함께 생성한다. 운동마다
`DATA_OWNER`, `BACKEND_REVIEWER`, `PM_REVIEWER`, `DOMAIN_REVIEWER` 네 역할의 DRAFT
증적 행이 있으며, 검토 상태를 변경할 때는 내부 비식별 reviewer reference, evidence
reference 및 timezone이 포함된 ISO 8601 시각이 필요하다.

작성한 매핑 결과와 증적 결과를 원본 배치에 대조해 검증한다.

```powershell
python data/scripts/validate_wger_gym_review_results.py `
  "data/validation/review_batches/<gym-core-review-v0.2.0>" `
  "<작성한-mapping-results.csv>" `
  "<작성한-evidence-results.csv>"
```

원천 ID·이름 등 불변 필드가 바뀌거나, `INCLUDE`/`MERGE` 행에 필수 검토 상태와 역할별
증적이 없으면 실패한다. 검증 성공도 프로덕션 승격을 의미하지 않으며 결과의
`production_eligible`은 항상 `false`다.

## 운동 카탈로그 seed 생성

`build_exercise_catalog_seed.py`는 승인 증적이 없으면 아무것도 만들지 않습니다.

검토 배치에는 `docs/DATA_MODEL.md` 5.2절이 요구하는 값 중 일부가 없습니다. 운동 유형,
운동 패턴, 난이도, 수행 시간, 휴식, 실행 안내는 별도 attribute 시트에 도메인 검토자가
작성합니다. 매핑 검토에서 `INCLUDE`/`MERGE`가 나온 뒤 템플릿을 만듭니다.

```powershell
python data/scripts/build_exercise_catalog_seed.py template kspo `
  "<batch>" "<mapping-results.csv>" --out "<attributes.csv>"
```

무엇이 남았는지 확인합니다. 이 명령은 실패시키지 않고 보고만 합니다.

```powershell
python data/scripts/build_exercise_catalog_seed.py readiness kspo `
  "<batch>" "<mapping-results.csv>" "<evidence-results.csv>" `
  --attributes "<attributes.csv>" `
  --taxonomy-registry data/normalized/exercise_taxonomy_codes.json
```

모든 조건이 충족되면 seed를 만듭니다.

```powershell
python data/scripts/build_exercise_catalog_seed.py build kspo `
  "<batch>" "<mapping-results.csv>" "<evidence-results.csv>" `
  "<attributes.csv>" "<taxonomy-registry.json>" --version-code v0.1.0
```

다음 중 하나라도 어긋나면 산출물을 만들지 않고 실패합니다.

- review batch 해시 검증 실패
- mapping·evidence가 기존 결과 validator를 통과하지 못함
- taxonomy registry가 `APPROVED`가 아님
- 운동에 `DOMAIN_REVIEWER`의 `DOMAIN_APPROVED` 증적이 없음
- attribute 필수 값 누락, 승인되지 않은 코드 사용
- `default_transition_seconds`가 10~20 범위 밖
- `body_area_code`가 `docs/DOMAIN_RULES.md`의 13개 코드에 없음
- 정규화 ID 중복 또는 한국어 표시명 중복

taxonomy registry는 2026-08-11에 개발 리드가 승인했습니다. 검토 완료 행이 0건인 동안에는
`build`가 계속 실패합니다.
생성된 seed도 `production_eligible=false`이며 DB 적재는 별도 승격 게이트가 필요합니다.

## 운동 안전 규칙 생성

`build_exercise_safety_rules.py`는 `docs/DATA_MODEL.md` 5.9절의 `exercise_safety_rules`
행을 만듭니다. 승인된 카탈로그 seed의 부하 부위와
`normalized/exercise_safety_rule_policy.json`에서만 도출하며 값을 추측하지 않습니다.

```powershell
python data/scripts/build_exercise_safety_rules.py build `
  data/generated/exercise-catalog-seed-wger-tranche1-v0.1.0 `
  data/generated/exercise-catalog-seed-kspo-tranche1-v0.1.0 `
  --version-code tranche1-v0.1.0

python data/scripts/build_exercise_safety_rules.py verify `
  data/generated/exercise-safety-rules-tranche1-v0.1.0
```

`coverage` 명령은 부위·심각도별로 선택 가능한 운동이 남는지 보고합니다.
`docs/DOMAIN_RULES.md` 4.3이 목표 보존형 대체를 요구하므로, 남는 운동이 없으면 대체가
불가능하다는 뜻입니다.

다음 중 하나라도 어긋나면 아무것도 만들지 않고 실패합니다.

- 정책 파일이 `APPROVED`가 아님
- seed 해시 불일치 또는 `DOMAIN_APPROVED`가 아닌 운동 포함
- **패턴 규칙이 그 패턴의 어떤 운동에서 성립하지 않음** (과일반화 차단)
- `exercise`와 `movement_pattern` 중 정확히 하나가 아닌 행
- 심각도 구간이 뒤집혔거나 `NONE`을 포함
- `body_area_code`가 `docs/DOMAIN_RULES.md`의 13개 코드에 없음

`SEVERE`는 `docs/DOMAIN_RULES.md` 4.2에 따라 세션 단위 `REST`이므로 이 규칙표는 `MILD`와
`MODERATE` 판단에 사용합니다. 범위와 한계는
[../normalized/SAFETY_RULES_DECISION.md](../normalized/SAFETY_RULES_DECISION.md)에 있습니다.

## 한국어 표시명 검수 규칙

`korean_display_name_rules.py`는 두 트랙의 결과 validator가 함께 사용하는 표시명 규칙이다.
wger snapshot에는 한국어 번역이 0건이므로 모든 한국어 명칭은 사람이 작성하며, 이 모듈은
번역을 생성하지 않고 형식만 검사한다.

`INCLUDE`/`MERGE` 행의 표시명은 한글을 포함해야 하고, 앞뒤 공백·제어문자가 없어야 하며,
배치 안에서 중복될 수 없고, 진단·치료·처방·재활 등 의료 표현을 쓸 수 없다. 한글이 없는
원천명을 그대로 복사한 행은 반려한다. `T바 로우`처럼 한글과 함께 쓰는 로마자는 허용하고,
macOS에서 입력한 NFD 한글은 NFC로 정규화해 비교한다.

상세 근거는 [REVIEW_RESULTS_GATE.md](../validation/REVIEW_RESULTS_GATE.md)를 따른다.

## 최종 대표운동 카탈로그 v2

`build_final_exercise_catalog_v2.py`는 기존 검수 원본을 변경하지 않고 최종본임을
명시한 별도 산출물을 생성한다. 2026-08-21 전문가 taxonomy 승인 이력은
`REVIEW_REQUIRED_*` family 값을 final family 코드로 실제 치환한 뒤 reviewer·시각과
함께 기록한다. 상태만 변경하는 승격은 허용하지 않는다. `target_muscle`,
주동·보조 부위, 난이도와 FITT는 최신 정규화본인
`catalog_enrichment_v3_fitt.csv`의 선정 NEX 행에서 가져오며, taxonomy의 이전
자유 텍스트 target을 다시 복사하지 않는다.

```bash
python3 data/scripts/build_final_exercise_catalog_v2.py
```

출력 디렉터리는 `data/generated/exercise-catalog-v2.0.0-final/`이며 핵심 파일은 다음과 같다.

- `representative_exercises_v2_final.csv`: 102 REX, 한·영명, 영문 body-focus,
  `primary_body_area_codes`·`secondary_body_area_codes`, 난이도, FITT/MET와 NEX 연결
- `stable_code_registry_v2.json`: REX와 불변 `stable_code`의 생성 결과. family·movement pattern·장비
  구분자를 사용하며, 명시적 대표운동 결정은 `data/normalized/v2_representative_decisions.json`에서 읽는다.
- `exercise_alternatives_v2_final.csv`: 대표운동 기준의 방향성 대체 관계
- `safety_rules_v2_final.jsonl`과 `representative_exercise_safety_mapping_v2_final.csv`: 정책과 REX↔rule bridge의 분리
- `finalization_validation_report.json`: 항목별 승인/검수 대기 수와 산출물 SHA-256

검수되지 않은 필수값이 남아 있으면 `finalization_validation_report.json`의
`runtime_json_eligible`가 `false`가 된다. 이 경우 runtime JSONL을 생성하거나 운영 승인 상태로
승격하지 않고, 입력 원본·결정 파일·생성기를 수정한 뒤 전체 산출물을 재생성한다.

도메인 검수 완료 후 JSONL을 실제로 구조화하고 Pydantic·manifest를 검증하려면 다음 materializer를
실행한다. 이 단계의 `DOMAIN_APPROVED`는 도메인 검수 완료 증적이며, 권리·운영 승격 조건 전에는
manifest의 `production_eligible=false`를 유지한다.

```bash
python3 data/scripts/build_v2_runtime_artifacts.py
```

출력은 `data/generated/exercise-catalog-v2.0.0-final/runtime/` 아래의 대표운동·대체운동·안전규칙
JSONL과 각 manifest다. 생성기 입력이 누락되거나 Pydantic, 해시, 건수, 버전 검증이 실패하면
fail-closed로 종료한다.

V2 최종 파일의 서비스 스키마 컬럼명 정렬 결과와 데이터 담당자 보완 요청은
[`data/reports/V2_SCHEMA_ALIGNMENT_REVIEW.md`](../reports/V2_SCHEMA_ALIGNMENT_REVIEW.md)에 기록한다.
최종 파일은 서비스 스키마와 의미가 같은 중복 컬럼을 스키마 이름으로 통일하며, 원천·검토용 컬럼은 유지한다.

대표운동 콘텐츠와 안전 문구는 최종 taxonomy를 입력으로 다시 생성한다.
생성된 콘텐츠는 자동 승인하지 않는다.

```bash
python3 data/scripts/generate_representative_content_safety.py \
  --input data/generated/exercise-catalog-v2.0.0-final/representative_exercise_taxonomy_v2_final.csv \
  --output-dir data/generated/representative-exercise-content-safety-v0.1.0
```

새 pattern bridge rule은 `INACTIVE_PENDING_DOMAIN_APPROVAL`로만 내보내며, 생성기가
운영 활성화하지 않는다. 원본 미디어는 기본 생성기에서 처리하지 않는다. Gymvisual 미디어를
연결할 때는 `data/scripts/sync_gymvisual_media.py --mapping-only`로
`gymvisual_media_mapping_manifest.csv`를 생성하고, 필요 시 같은 스크립트의 S3 모드로 기존
`images/`·`videos/` 객체를 보존한 채 `catalog-media/gymvisual/<stable_code>/` canonical alias만
추가한다. 원본 S3 key는 매핑 manifest에만 남기며 `media_assets_v2_final.csv`의 `s3_key`에는
canonical GIF key만 기록한다. 권리 승인이 없으면 최종 산출물의 `rights_review_status`는
`PENDING`이고 `production_eligible=false`다.

v2.0.2 통합 미디어 매핑은 `media_assets_v2_0_2.csv`의
`source_origin_code`(KSPO/WGER/GYMVISUAL 등), 원천 추적용 `source_track`,
원천 식별자 `source_identity`, 검증 결과 `source_identity_validation`을 사용한다.
통증 Alternative record는 `source_origin_code=PAIN_ALTERNATIVE_POLICY`를 보존하되,
`source_identity`는 이름 일치 또는 `alternative_source_base_exercise_id`로 확인한
실제 미디어 원천 운동의 ID를 사용한다. 원래 정책 record ID는
`record_source_identity`에 남기고, 미디어 원천은 `media_source_origin_code`와
`media_source_match_method`로 구분한다. Gymvisual의 `source_identity`는 앞자리 0을
보존한 숫자 문자열이어야 한다.

각 안전 규칙의 `pain_score_decisions`는 `pain-intensity-map-v1`에 따라 1–3점에서 규칙별
부하 조절 또는 안전 대체를 요구하고, 4–6점에서 검수된 안전 대체나 저강도 회복 콘텐츠만
허용한다. 저강도 회복에는 해당 부위에 대해 별도 승인된 스트레칭만 포함할 수 있다. 7–10점은
운동 선택보다 먼저 적용되는 세션 `REST`이며, 어떤 구간이든 안전한 계획이 없으면 `REST`한다.

v2.0.2 통증 Alternative는 다음 순서로 생성한다. `NRS_1_3`·`NRS_4_6`만 관계로 만들고,
`NRS_7_10`은 Alternative map에 넣지 않는다. 난이도 정책 변경으로 추가된 29건은 별도
재검수 batch에 남기며 승인 집합에서 제외한다.

```bash
python3 data/scripts/build_v2_0_2_discomfort_alternative_map.py
python3 data/scripts/review_v2_0_2_discomfort_alternative_map.py
python3 data/scripts/resolve_v2_0_2_discomfort_alternative_concerns.py \
  --difficulty-review data/generated/exercise-catalog-v2.0.2-final/integrity/alternative_difficulty_policy_review_batch_v2_0_2.jsonl
```

현재 resolver 결과는 승인 대상 관계 1,104건, 제거 384건, 난이도 재검수 pending 29건이다.
`resolved_discomfort_alternative_map_v2_0_2.jsonl`만 importer 변환 대상이며, pending map과
`REVIEW_REQUIRED` safe variant는 적재·런타임 사용 대상에서 제외한다.

## 공식 신체활동 근거와 참조 데이터

공식 URL의 응답 해시와 최소 원천 사실을 수집한다. 원문 HTML·PDF는 저장소에 보존하지
않으며, 일반 HTTP 클라이언트가 차단된 CDC 페이지는 브라우저로 확인한 구조화 사실의
해시임을 별도로 표시한다.

```powershell
python data/scripts/collect_physical_activity_guidelines.py collect `
  --retrieved-at "<ISO-8601 timezone timestamp>"
python data/scripts/collect_physical_activity_guidelines.py verify
```

검증된 원천에서 일반 성인 주간 FITT, 절대·상대 강도, Compendium 관련 활동 참조를 만든다.

```powershell
python data/scripts/build_physical_activity_reference.py build
python data/scripts/build_physical_activity_reference.py verify
```

결과는 `DRAFT`, `AGENT_ONLY`, `production_eligible=false`다. MET 값은 변경하지 않고,
운동 카탈로그와 자동 연결하지 않으며, 개인 처방이나 안전 veto 대체에 사용할 수 없다.

최종 MET 매핑은 데이터 소유자가 명시적으로 검수한 경우에만 별도 승인 manifest를 적용한다.
`met_final_approval.csv`는 직접 대응하지 않는 한발 균형운동의 02150 Hatha yoga 프록시를
기록하고, `met_domain_approval_manifest.csv`는 전체 208개 NEX 매핑에 대한 소유자 승인 범위를
기록한다. 다음 명령은 승인 증적과 공식 Compendium URL을 검증한 뒤에만 `DOMAIN_APPROVED`와
`production_eligible=true`를 적용한다.

```bash
python3 data/scripts/apply_final_met_approval.py \
  --mapping data/generated/exercise-met-mapping-v0.1.0/exercise_met_mapping_reviewed.csv \
  --approvals data/validation/review_results/met_final_approval.csv \
  --output-mapping /tmp/met_approved.csv \
  --output-change-log data/generated/exercise-met-mapping-v0.1.0/met_final_approval_change_log.csv
python3 data/scripts/promote_all_met_approvals.py \
  --mapping /tmp/met_approved.csv \
  --manifest data/validation/review_results/met_domain_approval_manifest.csv \
  --output-mapping data/generated/exercise-met-mapping-v0.1.0/exercise_met_mapping_reviewed.csv \
  --output-change-log data/generated/exercise-met-mapping-v0.1.0/met_domain_approval_change_log.csv
```

이 승격은 MET 필드에만 적용되며, 대표운동 target muscle·콘텐츠·안전규칙·대체관계·미디어
권리 검수 상태를 자동 승인하지 않는다. 최종 대표 카탈로그는 해당 독립 게이트가 남아 있으면
`FINAL_CATALOG_PENDING_TARGET_MUSCLE_REVIEW_AND_MEDIA_RIGHTS`로 유지된다.

## Gym Visual 공통 정렬과 공백 검토

`align_source_candidates.py`는 KSPO 391건·wger 400건 전체 profile 인벤토리를 Gym Visual과
같은 후보 컬럼·값 코드로 정렬하고, 기존 검토 결과는 overlay한다. 원천 값이 없거나 서로
다른 해석이 필요한 경우 `REVIEW_REQUIRED`로 남기며 자동으로 채우지 않는다. 산출물은
`validation/review_batches/`와 `validation/profiles/`에만 기록한다.

`build_source_gap_review.py`는 Gym Visual strength/cardio/mobility 선정 결과의 커버리지를
먼저 계산하고, `normalized/source_gap_policy.json`에 선언된 실제 공백만 KSPO·wger 전체
후보에서 검토 큐로 보낸다. 현재 KSPO MVP 범위에서 3건이 `HOME_LOW_IMPACT_CARDIO` 검토 후보로
추출되며, family/variant는 대체 관계가 아니다. 이 단계에서는 catalog·safety rule·
alternative generated 데이터를 만들지 않는다.

## V2 처방·goal tag와 backend bundle

### v2.0.2 독립 Variant/별도운동 바인딩

Alternative target 운동의 카탈로그 편입 정책은 Alternative 관계와 운동 풀을 분리한다.
현재 통증 비부하 변형은 `alternative_only=true`를 보존해 Alternative provenance를 남기지만
`general_pool_included=true`로 일반 운동 풀에도 포함한다. v2.0.1 Alternative target 목록 중
v2.0.2에서 누락된 대표운동은 아래 두 원천 파일의 stable code를 대조해 canonical 원천에서
`REPRESENTATIVE`로 복원한다. 복원 대상은 운동 레코드뿐이며, 이전에 탈락한 Alternative 관계를
자동 복구하지 않는다.

- 대상 목록: `generated/exercise-catalog-v2.0.1-final/exercise_alternatives_v2_final.csv`
- 대표운동 원천: `generated/exercise-catalog-v2.0.1-final/representative_exercises_v2_final.csv`
- 복원 canonical 원천: `generated/exercise-catalog-v2.0.2-final/canonical_exercises_v2_final.jsonl`
- 반영 생성기: `scripts/prune_v2_0_2_user_catalog.py`

Variant와 통증 Alternative 전용 `SEPARATE_EXERCISE`는 대표운동 값을 상속하지 않고,
최신 원천 파일(`normalized/catalog_enrichment_v3_fitt.csv`,
`exercise_safety_mapping_v2.csv`, draft `goal_tag_links.jsonl`)의 운동명·NEX 매핑으로
독립 FITT·Safety·Goal 행을 생성한다. 생성 후에는 반드시 통합 검증과 DB 적재 준비 검사를
순서대로 실행한다.

```bash
python3 data/scripts/materialize_v2_0_2_independent_bindings.py
python3 data/scripts/validate_v2_0_2_integrated_catalog.py
python3 data/scripts/verify_v2_0_2_db_load_readiness.py
```

결과는 `variant_safety_fitt_mapping_v2_0_2.jsonl`,
`prescriptions/prescription_profiles.jsonl`, `runtime/safety_rules.jsonl`,
`prescriptions/goal_tag_links.jsonl` 및 `integrity/independent_bindings_materialization_report_v2_0_2.json`에
기록된다. 소스 템플릿 ID가 최신 템플릿 레지스트리에 없는 경우에는 운동군 템플릿 fallback과
그 사유를 행의 `template_resolution_code`에 남긴다.

생성 단계는 계속 `production_eligible=false`를 유지한다. 최종 검수가 일괄 완료된 경우에는
행별 사유를 반복 기록하지 않고 final `manifest.json`의 `batch_approval`에 승인 참조·시각·범위와
승인 근거를 기록한 뒤, 통합 validator와 DB-load readiness를 다시 실행한다. validator는 해당
일괄 승인 범위가 final 170건, Variant 15건, 난이도 변경 29건, Alternative 1,104건,
Media/Rights 102건과 일치할 때만 승인 상태를 유지한다.

V2 102개 대표운동은 legacy 처방 결과와 분리된 review input을 사용한다.

```bash
python3 data/scripts/build_v2_prescription_review_input.py --force
python3 data/scripts/validate_v2_prescription_review_input.py \
  data/generated/exercise-catalog-v2.0.0-final/representative_exercises_v2_final.csv \
  data/validation/review_results/v2_prescription_review_input.csv \
  --policy data/normalized/v2_prescription_review_policy.json
python3 data/scripts/build_v2_prescriptions.py --force
```

입력은 102개 goal tag와 137개 phase profile을 만든다. JSONL은 직접 수정하지 않고
generator를 다시 실행한다. review policy, review input, prescription manifest는 모두
DRAFT/`production_eligible=false`이며 backend 기록으로 자동 승인되지 않는다.

runtime을 backend importer 형식으로 패키징한다.

```bash
python3 data/scripts/build_v2_backend_bundle.py --force
V2_UV_CACHE=/private/tmp/skn30-uv-cache UV_CACHE_DIR=$V2_UV_CACHE \
  uv run python data/scripts/validate_v2_backend_bundle.py
V2_UV_CACHE=/private/tmp/skn30-uv-cache UV_CACHE_DIR=$V2_UV_CACHE \
  uv run python data/scripts/build_v2_approval_registry_candidate.py
```

bundle은 `catalog/seed_manifest.json`, `safety/rules_manifest.json`,
`alternatives/alternatives_manifest.json`, `prescriptions/prescription_manifest.json`을
제공한다. `bundle_manifest.json`은 내부 input과 산출물의 path/hash/byte/count를 관리한다.
v2.0.2 final 적재에서는 별도 bundle glob을 사용하지 않고 final `manifest.json`의
`import_contract.canonical_payloads`에 지정된 6개 payload만 읽는다. 그 밖의 생성·검수
산출물은 `generated/exercise-catalog-v2.0.2-final/audit/` 아래에 보관한다.
backend V2 code set은 `v2_backend_code_projection.json`으로 직접 전달하며 runtime 원본을
변환하지 않는다. 기존 v2.0.1 bundle의 alternatives 키는
`(source, alternative, reason, goal, rule_version)`이며, v2.0.2 통증 관계를 적재할 때는
여기에 `(pain_discomfort_area_code, condition_code)`를 보존하고
`service_action_code`, `target_strategy_code`도 함께 전달해야 한다. 이 필드들은 DB
마이그레이션 `0028_discomfort_alt_conditions`의 nullable 컬럼에 적재된다.
통증 map CSV/JSONL을 그대로 importer에 넣을 수는 없으며, source/target stable code,
goal 보존, difficulty delta, 승인 상태를 importer schema로 변환하는 별도 materialization과
hash/count 검증이 필요하다. `catalog_data_load`, `catalog_activate`, ACTIVE 전환은 이
작업에서 실행하지 않는다.
