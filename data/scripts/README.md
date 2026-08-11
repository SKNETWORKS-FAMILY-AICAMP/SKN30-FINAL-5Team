# Data scripts

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
