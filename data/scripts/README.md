# Data scripts

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
운영 활성화하지 않는다. 원본 미디어는 처리하지 않는다. 별도 권리 승인 입력이 없으면
`media_assets_v2_final.csv`는 header-only로 남고 S3 업로드·사용자 노출은 발생하지 않는다.

각 안전 규칙의 `pain_score_decisions`는 `pain-intensity-map-v1`에 따라 1–3점에서 규칙별
부하 조절 또는 안전 대체를 요구하고, 4–6점에서 검수된 안전 대체나 저강도 회복 콘텐츠만
허용한다. 저강도 회복에는 해당 부위에 대해 별도 승인된 스트레칭만 포함할 수 있다. 7–10점은
운동 선택보다 먼저 적용되는 세션 `REST`이며, 어떤 구간이든 안전한 계획이 없으면 `REST`한다.

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
backend V2 code set은 `v2_backend_code_projection.json`으로 직접 전달하며 runtime 원본을
변환하지 않는다. alternatives는 `(source, alternative, reason, goal, rule_version)` 키로
285건을 손실 없이 보존한다. `catalog_data_load`, `catalog_activate`, ACTIVE 전환은 이
작업에서 실행하지 않는다.
