# External exercise data pipeline

## 2026-08-11 MVP v0.2 현황

- KSPO 50개와 wger 60개 리뷰 후보를 모두 결정했다: 포함 50, 제외 60, 미결 0.
- 최신 생성물은 `generated/*-mvp-v0.2.0`이며 카탈로그 50개와 안전 규칙 277개다.
- 검토 방법은 `AGENT_ONLY`이고 외부 전문가 승인으로 해석하지 않는다.
- 모든 결과는 `production_eligible=false`인 DRAFT다.
- 현재 MVP 수집은 마감하고 대체 관계·golden scenario 검증을 우선한다.
- 추가 수집은 안전 필터 후 선택 후보 부족, 위치·장비·패턴 결손, 대체 운동 부족이
  실제 테스트로 확인될 때만 재개한다.
- 상세 수집 현황은 `reports/DATA_COLLECTION_REPORT.md`, 전처리·분포·검증은
  `reports/DATA_PREPROCESSING_REPORT.md`를 참조한다.

## 1차 수동 검토 배치

profile의 `MVP_SCOPE_REVIEW` 후보는 곧바로 정규화하거나 승인하지 않습니다. 먼저
`build_kspo_fitness100_review_batch.py`로 재현 가능한 50개 검토 순서를 만들고 다음 항목을
담당자별로 채웁니다.

- 데이터/기술: 중복 경계, 원천 근거, 정규화 ID 후보
- PM/권리: 콘텐츠 및 미디어 이용 범위
- 도메인 검토자: taxonomy, 초보자 적합성, 실행 dosage, 자세 문구, 안전, 대체 관계
- 개발 리드: 리뷰 증적과 프로덕션 승격 게이트

검토 순서는 원천 장소·도구 조합의 다양성을 위한 운영 큐일 뿐입니다. 배치 포함 여부를
운동의 안전성, 품질 또는 최종 카탈로그 포함 결정으로 해석하지 않습니다.

KSPO 홈·맨몸 트랙과 wger 헬스장 트랙은 모두 review batch v0.2.0에서 검토 결과 입력 열과
역할별 증적 템플릿을 함께 제공하며, 같은 결과 게이트 규칙을 사용한다.
[validation/REVIEW_RESULTS_GATE.md](validation/REVIEW_RESULTS_GATE.md)를 따른다.

## 1. 목표

외부 운동 데이터를 출처와 라이선스가 추적 가능한 원문으로 수집하고, 기술 검증과
도메인 승인을 분리해 프로덕션 카탈로그로 승격한다. 외부 데이터는 운동 추천이나
안전 판단에 바로 사용하지 않는다.

## 2. 초기 범위

기본 원천은 공공데이터포털 데이터셋 `15108846`,
`서울올림픽기념국민체육진흥공단_국민체력100 동영상 정보`다. 헬스장 기구·프리웨이트
종목의 명칭과 장비 커버리지를 보강하기 위해 wger exercise catalog를 별도 원천으로
수집한다.

- 장점: 성인, 체력요인, 운동부위, 운동도구 등 MVP 카탈로그 후보를 찾는 데 필요한
  메타데이터를 제공한다.
- 이용 조건: 공공누리 제1유형(출처표시), 제3자 권리 포함.
- 제한: 영상과 썸네일 파일은 내려받지 않는다. API JSON 메타데이터만 수집한다.
- 상태: 수집 결과는 항상 `DRAFT`이며 자동으로 승인 데이터가 되지 않는다.

wger 보강 원천은 공개 API JSON만 수집한다. 운동·번역·미디어 항목의 개별 라이선스와
저작자 표시를 보존하고 이미지·동영상 바이너리는 수집하지 않는다. wger의 이름·장비·근육
필드는 KSPO 필드로 합쳐 표시하지 않으며 source-specific provenance를 유지한다.

체력측정 개인 결과 API, 사용자 데이터, 웨어러블 원시 데이터는 이 파이프라인의
수집 대상이 아니다.

## 3. 단계와 산출물

```text
official API
  -> immutable raw JSON pages + SHA-256 manifest (DRAFT)
  -> source field profiling and mapping proposal
  -> representative exercise-family/variant review batch (CSV/XLSX)
  -> normalized catalog candidate (DRAFT)
  -> schema, duplicate, reference and duration validation
  -> TECH_REVIEWED
  -> PM license/content review
  -> external exercise/health professional review
  -> DOMAIN_APPROVED
  -> generated seed + DB import
```

### Gym Visual 변형 경계

`data/validation/profiles/gymvisual_strength_profile.json`의 INCLUDE 대표 운동을
기준으로 `data/scripts/build_gymvisual_variant_review.py`가 동일 target·family
어휘와 장비·장소·그립·자세·지지·스탠스·실행 차이를 함께 확인할 수 있는 후보만 만든다.
`v.2` 같은 이름만의 차이는 후보로 만들지 않는다. 이 단계의 산출물은 다음 두
CSV이며, 아직 최종 family 확정이나 대체 관계가 아니다.

대표 운동 하나당 변형 후보는 최대 5개로 제한한다. 자동 우선순위는 `HOME` 장소,
맨몸·밴드·덤벨 등 입문자 친화 도구, 대중적인 기본 운동명 순서이며, Gym Visual에
인기도 필드가 없으므로 마지막 기준은 명시된 이름 토큰 기반의 보수적 proxy다.
스트레칭·가동성 후보와 동일 이름·장비의 원천 중복은 변형 검토 대상에서 제외한다.

- `data/validation/review_batches/gymvisual_variant_review.csv`: 사람 검토용 배치
- `data/validation/review_results/gymvisual_variant_reviewed.csv`: 검토 결과 입력용 `PENDING` 템플릿

변형 후보는 `NOT_CREATED_BY_DESIGN`으로 표시한다. 통합 카탈로그 확정, 부하 검토,
전문가 안전 정책 검토와 안전 규칙 생성을 통과한 뒤에만 대체 관계 후보를 별도
생성한다. 기존 56개 카탈로그, 안전 규칙 354건, 대체 관계 238건 산출물은 이
단계의 입력·참조 대상이 아니며 덮어쓰지 않는다.

### 스트레칭·가동성 선정 경계

근력·유산소 카탈로그와 별도로 `data/scripts/profile_gymvisual_mobility.py`가
`normalized/mobility_selection_policy.json`의 선언형 후보 목록을 원천 스냅샷에서
읽어 자동 프로파일을 만든다. 현재 프로파일은 초보·복귀 사용자 활용성, 신체 부위와
가동성 목표 커버리지, family 중복, 난이도 다양성을 기준으로 35개 후보를 기록한다.
이는 `MOBILITY`/`MOBILITY_STRETCH` 후보 표기일 뿐, 안전성·금기·실행 용량의 확정이 아니다.

`data/scripts/build_gymvisual_mobility_review.py`는 다음 CSV를 만든다.

- `data/validation/review_batches/gymvisual_mobility_review.csv`: family·variant·초보자 적합성·부하·안전 검토 배치
- `data/validation/review_results/gymvisual_mobility_reviewed.csv`: 사람 검토 결과 입력용 `PENDING` 템플릿

스트레칭은 근력 운동의 목표 보존 대체 관계로 자동 연결하지 않는다. 예를 들어
스쿼트와 대퇴사두근 스트레칭은 서로 다른 목표이므로 대체 관계가 아니다. 사람 검토,
통합 카탈로그 확정, 부하 검토와 도메인 안전 정책 검토가 모두 끝나기 전에는 mobility
generated seed·안전 규칙·대체 관계를 생성하지 않는다.

### KSPO·wger 공통 후보 정렬과 공백 보충

`align_source_candidates.py`는 KSPO·wger의 검토 결과를 Gym Visual 후보 공통 컬럼과
값 코드로 투영한다. 원천 CSV는 입력으로만 읽고, `candidate_id`, `source_name`,
`source_equipment`, `target`, `movement_pattern_code_candidate`,
`exercise_family_candidate`, `variant_group_candidate`, `equipment_code_candidate`,
`location_code_candidates`, `difficulty_code_candidate`,
`beginner_suitability_candidate`를 같은 이름으로 제공한다. 원천 근거가 없는 값은
추정하지 않고 `REVIEW_REQUIRED`로 남긴다. 원천별 식별자·라이선스·검토 결정은 별도
provenance 컬럼으로 보존한다.

```bash
python data/scripts/align_source_candidates.py
```

결과는 `validation/review_batches/gymvisual-source-alignment-v0.4.0/`의 CSV·JSONL과
`validation/profiles/gymvisual_source_alignment-v0.4.0.json`이며, generated seed는
만들지 않는다.

`build_source_gap_review.py`는 Gym Visual 선정 결과를 먼저 집계한 뒤 실제 공백만
KSPO 우선·wger 보완 순서로 검토 큐에 넣는다. 현재 확인된 공백은 `HOME_LOW_IMPACT_CARDIO`
1건(선정 2건, 최소 3건)이고, 머신·케이블·밴드와 mobility stretch는 이미 커버되어
추가 후보를 만들지 않는다. 전체 profile 인벤토리 KSPO 391건·wger 400건을 다시
정렬한 결과, KSPO MVP 범위에서 원천명 기반의 저충격 홈 유산소 검토 후보 3건을 추출했다.
이 3건은 저충격·유산소·초보자 적합성을 확정한 데이터가 아니라 사람 검토용 후보이며,
`source_gap_review.csv`에서 `REVIEW_REQUIRED`로 남긴다.

```bash
python data/scripts/build_source_gap_review.py
```

공백 보충 이후에도 family/variant 정리, 통합 카탈로그 확정, 부하 검토, 도메인 안전
검토, 안전 규칙 생성, 안전 규칙 통과 후보 간 대체 관계 생성을 순서대로 수행한다.
기존 카탈로그 56종·안전 규칙 354건·대체 관계 238건은 읽기 전용 기준으로만 보존한다.

승격 조건은 다음과 같다.

| 단계 | 자동화 가능 | 승인 책임 |
|---|---|---|
| 원문 수집·해시·페이지 수 검증 | 예 | 데이터 담당 |
| 필드 정규화·중복 후보 생성 | 예 | 백엔드/데이터 기술 검토 |
| 대체 운동 후보·통증 충돌 초안 | 후보 생성만 가능 | PM + 외부 전문가 |
| FITT/시간 메타데이터 | 범위·형식 검증만 가능 | 외부 전문가 |
| 프로덕션 seed 승격 | 승인 증적 검사만 가능 | 개발 리드 최종 게이트 |

## 4. 실패 폐쇄 원칙

- API 성공 코드, 페이지 수, 전체 레코드 수가 일치하지 않으면 snapshot을 만들지 않는다.
- 원문 파일 해시가 달라지거나 manifest가 누락되면 검증에 실패한다.
- 출처, 라이선스, 수집 시각, pipeline version, review status가 없으면 실패한다.
- `DOMAIN_APPROVED` 증적이 없는 데이터는 generated seed로 승격하지 않는다.
- 원천의 질환명이나 운동 분류를 제품의 통증 제외 규칙으로 자동 변환하지 않는다.
- MET, RPE, 반복수, 휴식시간, 금기사항을 임의로 채우지 않는다.

## 5. 다음 구현 순서

1. KSPO와 wger snapshot 및 profile의 무결성을 재검증한다.
2. 헬스장 핵심 운동군별 source-to-normalized mapping 후보를 사람이 검토한다.
3. 한국어 표시명, 장비 taxonomy, 중복·변형 경계를 별도 필드로 확정한다.
4. MVP 30~50개 후보 선정 기준과 홈·헬스장 커버리지 목표를 문서화한다.
5. 공통 exercise schema와 source별 provenance 구조를 리뷰한다.
6. 실행 안내, FITT, 안전·대체 관계를 별도 검수 데이터로 작성한다.
7. 승인 증적을 요구하는 seed generator를 구현한다.

초기 후보는 성인 대상, 초보자 설명이 있는 운동, 홈·헬스장·걷기/가벼운 러닝·
스트레칭/코어 범위를 우선한다. 후보 선정은 다양성과 MVP 커버리지를 위한 것이며
안전 승인을 대신하지 않는다.

### 현재 상태

1번은 완료했다. KSPO·wger snapshot과 profile, 두 트랙의 v0.2.0 배치가 모두 해시
검증을 통과한다.

2번부터 7번까지 tranche 1(24종)에 대해 완료했다. 개발 리드가 데이터 파트 총괄 권한으로
네 검토 역할을 AI 에이전트에 위임했고, 그 결정과 한계를
[validation/review_results/TRANCHE1_REVIEW_DECISION.md](validation/review_results/TRANCHE1_REVIEW_DECISION.md)에
기록했다. 결과는 `generated/`의 두 seed다.

| 트랙 | 검토 완료 | seed |
|---|---:|---|
| wger 헬스장 | 14 / 60 | `exercise-catalog-seed-wger-tranche1-v0.1.0` |
| KSPO 홈·맨몸 | 10 / 50 | `exercise-catalog-seed-kspo-tranche1-v0.1.0` |

두 seed 모두 `production_eligible`이 `false`다. DB 설계·적재를 진행할 수 있는 DRAFT
카탈로그이며 사용자 노출 승인이 아니다. 나머지 86행은 `PENDING`으로 남아 있고 같은
절차로 tranche 2를 진행한다.

6번의 안전 규칙도 같은 위임으로 작성했다. `scripts/build_exercise_safety_rules.py`가
승인된 seed의 부하 부위와 `normalized/exercise_safety_rule_policy.json`에서 규칙을
도출하며, 결과는 `generated/exercise-safety-rules-tranche1-v0.1.0`의 139행이다. 범위와
한계, 그리고 커버리지 공백은
[normalized/SAFETY_RULES_DECISION.md](normalized/SAFETY_RULES_DECISION.md)에 있다.

대체 관계(`exercise_alternatives`)는 아직 없다. 안전 규칙은 무엇을 빼는지만 정하고
무엇으로 바꿀지는 정하지 않는다.

칼로리 산식·계수는 개발 리드 결정으로 데이터 파트 범위에서 제외한다(2026-08-11).

3번과 5번의 taxonomy 코드는 `docs/API_CONTRACT.md`의 미확정 계약이므로 파이프라인이 임의로
정하지 않는다. 원천 어휘 실측과 승인된 문서 문장에서 도출한 제안을
[normalized/EXERCISE_TAXONOMY_CODE_PROPOSAL.md](normalized/EXERCISE_TAXONOMY_CODE_PROPOSAL.md)와
`normalized/exercise_taxonomy_codes.json`에 두었다. 개발 리드가 2026-08-11에
승인했으므로 결과 validator가 `review_taxonomy_code`의 목록 소속을 검사한다. `body_area_code`는 `docs/DOMAIN_RULES.md`에서 이미
확정되어 있다.

FITT·MET 참고 원천은 [FITT_REFERENCE_ASSESSMENT.md](FITT_REFERENCE_ASSESSMENT.md)에서
평가했다. 결론은 snapshot 수집 대상이 아니라는 것이다. MVP 스키마에 MET 컬럼이 없고,
세션 시간 구조는 이미 `docs/DOMAIN_RULES.md`에 확정되어 있으며, 해당 문서들은 공개
API가 아니라 라이선스 제한이 있는 저작물이다.

7번 seed generator는 `scripts/build_exercise_catalog_seed.py`로 구현했다. 승인 증적이
없으면 아무것도 생성하지 않는다. tranche 1 검토가 끝나 두 트랙 모두 `build`가 성공하며,
검토가 끝나지 않은 86행은 여전히 seed에 들어가지 않는다.

`readiness` 명령이 무엇이 비어 있는지 기계적으로 보고하므로, 남은 작업을 추정하지 않고
확인할 수 있다. 검토 배치에 없는 DATA_MODEL 필드는 `template` 명령이 만드는 catalog
attribute 시트에 도메인 검토자가 작성한다.

## 병합 카탈로그와 처방 산출물 (2026-08-20)

런타임은 단일 ACTIVE 카탈로그만 조회하므로 KSPO와 wger의 승인 seed를
`build_merged_catalog_seed.py`로 병합한다. 병합은 레코드 내용을 바꾸지 않으며 입력
manifest hash를 다시 검사하고 stable code 충돌과 한국어 표시명 중복을 fail-closed로
거부한다. 카탈로그 단위 source track은 `merged`, 운동 단위 source track/identity는 원본
값을 보존한다.

처방 파이프라인은 다음 순서를 따른다.

1. `prescription_review_authoring.py`로 운동별 직접 검수 결과를 작성한다.
2. `validate_exercise_prescription_review_results.py`가 CSV 계약, catalog 참조, timing mode,
   검수 증적과 HOME·GYM × 20/30/40/50분의 정확한 시간 해 존재를 검증한다.
3. `build_exercise_prescriptions.py`가 goal tag와 prescription profile을 분리된 JSONL 및
   manifest로 생성한다.
4. backend bundle importer가 catalog, safety rules, alternatives, goal tags,
   prescriptions를 한 transaction에서 적재한다.
5. 승인 registry와 migration은 정확한 version/hash/count에만 승인 metadata를 부여한다.
6. `catalog_activate`가 처방과 goal tag의 존재를 다시 확인한 뒤 단일 ACTIVE catalog로
   전환한다.

현재 고정 산출물은 catalog `merged-mvp-v0.4.0` 56종, safety rules
`merged-mvp-v0.5.0` 282건, alternatives `merged-mvp-v0.4.0` 238건, prescriptions
`merged-mvp-v0.1.0`의 goal tag 32건 및 profile 36건이다. generated manifest는 항상
production-ineligible로 남고, 운영 승인은 backend의 정확 일치 gate로만 표현한다.

### 원천 단위 주의

`training-video` endpoint의 한 행은 운동 하나가 아니라 영상에서 추출한 이미지
프레임일 수 있다. `row_num`이나 `img_file_nm` 개수를 운동 개수로 사용하지 않는다.
현재 profiling 단계의 검토 후보 키는 `(file_nm, trng_nm)`이며, 서로 다른 영상의
동일 운동명이 같은 운동인지 여부는 정규화 리뷰에서 결정한다. `vdo_len`은 영상
길이이므로 운동 수행시간으로 사용하지 않는다.

## V2 102개 처방·backend bundle (2026-08-25)

V2 대표운동 102개를 기존 legacy 처방 입력과 분리해 작성한다. review input은 V2 대표 CSV와
`normalized/v2_prescription_review_policy.json`에서 생성하며, stable code를 유일한 FK로
사용한다. 운동명·legacy 처방 결과를 재사용하지 않는다.

```bash
python3 data/scripts/build_v2_prescription_review_input.py --force
python3 data/scripts/validate_v2_prescription_review_input.py \
  data/generated/exercise-catalog-v2.0.0-final/representative_exercises_v2_final.csv \
  data/validation/review_results/v2_prescription_review_input.csv \
  --policy data/normalized/v2_prescription_review_policy.json
python3 data/scripts/build_v2_prescriptions.py --force
```

처방 산출물은 `generated/exercise-prescriptions-v2.0.0-draft/`의
`goal_tag_links.jsonl` 102건, `prescription_profiles.jsonl` 137건과 manifest다. 모든
version status는 `DRAFT`, `production_eligible`은 `false`다.

runtime 산출물을 backend importer 디렉터리 구조로 패키징하고 검증한다.

```bash
python3 data/scripts/build_v2_backend_bundle.py --force
V2_UV_CACHE=/private/tmp/skn30-uv-cache UV_CACHE_DIR=$V2_UV_CACHE \
  uv run python data/scripts/validate_v2_backend_bundle.py
V2_UV_CACHE=/private/tmp/skn30-uv-cache UV_CACHE_DIR=$V2_UV_CACHE \
  uv run python data/scripts/build_v2_approval_registry_candidate.py
```

bundle 내부 진입점은 `catalog/seed_manifest.json`, `safety/rules_manifest.json`,
`alternatives/alternatives_manifest.json`, `prescriptions/prescription_manifest.json`이며,
`bundle_manifest.json`이 각 내부 파일의 path·SHA-256·byte·record count를 기록한다.
현재 runtime alternatives 285건 중 통증 구간별 의미가 backend natural key와 충돌하는 2건은
importer projection에서 283건으로 축약된다. 원본 후보는
`alternatives/input/alternative_projection_conflicts.json`에 보존하며 projection은
`LOSSY_DRAFT_ONLY`다. 이 blocker가 해소되기 전에는 운영 적격으로 해석하지 않는다.
