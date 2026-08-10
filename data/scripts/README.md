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

이 스크립트는 Python 표준 라이브러리만 사용합니다. 수집 결과는 `DRAFT`이며
정규화 또는 프로덕션 seed가 아닙니다.

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
