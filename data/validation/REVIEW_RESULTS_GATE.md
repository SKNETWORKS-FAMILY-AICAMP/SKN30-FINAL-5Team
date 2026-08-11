# 검토 결과 게이트

상태: `DRAFT`  
validator version: `0.1.0`  
production eligible: `false`

두 원천 트랙이 같은 게이트 규칙을 사용한다.

| 트랙 | 배치 | mapping 파일 | validator |
|---|---|---|---|
| wger 헬스장 | gym-core-review v0.2.0 | `gym_core_review_batch.csv` | `validate_wger_gym_review_results.py` |
| KSPO 홈·맨몸 | review-batch v0.2.0 | `review_batch.csv` | `validate_kspo_fitness100_review_results.py` |

두 트랙 모두 `catalog_review_records_template.csv`를 증적 템플릿으로 사용한다. 승인 필드는
원천의 권리 위험이 달라 트랙별로 다르다. wger는 `review_license_status`, KSPO는
`review_media_rights_status`를 사용한다. KSPO 원천은 공공누리 제1유형이지만 제3자 권리가
포함될 수 있고 영상·썸네일을 재배포하지 않으므로 미디어 권리를 별도로 확인한다.

## 목적

검토자가 작성한 운동 매핑 결과와 역할별 증적을 원본 review batch에 대조한다. 이 게이트는
원천 identity 변경, 근거 없는 승인 및 안전 검수 누락을 실패 처리한다. 검증 성공은
normalized seed 생성이나 프로덕션 승격이 아니다.

## 계약 근거

`docs/DATA_MODEL.md`의 다음 계약을 사용한다.

- exercise의 프로덕션 사용은 `DOMAIN_APPROVED`만 가능하다.
- `catalog_review_records`는 대상, 상태, reviewer role, 내부 비식별 reviewer reference,
  evidence reference와 검토 시각을 보존한다.
- reviewer role은 `DATA_OWNER`, `BACKEND_REVIEWER`, `PM_REVIEWER`,
  `DOMAIN_REVIEWER`다.

외부 검수자의 실제 자격 확인, 계약 및 운영상 ID 발급 방식은 이 파이프라인에서 결정하지
않는다.

## 입력

1. 검증된 review batch v0.2.0
2. 배치의 mapping CSV를 복사해 작성한 mapping results
3. 배치의 `catalog_review_records_template.csv`를 복사해 작성한 evidence results

원본 파일은 manifest 해시 검증 대상이므로 직접 수정하지 않는다.

## 매핑 행 검증

- 원천 식별자, 원천명, 장비·도구, 라이선스 등 원천 필드는 변경할 수 없다.
  wger는 source ID와 UUID, KSPO는 `source_candidate_id`가 식별자다.
- `PENDING` 행은 미완료 상태로 검증 가능하지만 승인 후보가 아니다.
- `EXCLUDE`에는 제외 사유가 필요하다.
- `INCLUDE` 또는 `MERGE`에는 다음 값이 모두 필요하다.
  - 소문자 machine code 형식의 정규화 운동 ID
  - 한국어 표시명
  - 승인된 movement pattern 코드(대문자)
  - 검토된 초보자 적합성
  - 실행 안내, 라이선스(KSPO는 미디어 권리) 및 도메인 안전 상태 `APPROVED`

taxonomy 코드는 2026-08-11에 개발 리드가 승인했다. `review_taxonomy_code`는 형식이 아니라
`normalized/exercise_taxonomy_codes.json`의 `movement_pattern_code` 목록에 속해야 하며
표기는 대문자다. registry가 `APPROVED`가 아니면 검증 자체가 실패한다.

## 한국어 표시명 검수 규칙

wger snapshot에는 한국어 번역이 0건이고 KSPO 원천명은 영상 프레임 라벨이므로 모든
`review_display_name_ko`는 사람이 작성한다. 파이프라인은 번역을 생성하거나 제안하지
않으며 작성된 값의 형식만 검사한다.

`INCLUDE` 또는 `MERGE` 행에 다음을 적용한다.

| 규칙 | 근거 |
|---|---|
| 한글이 최소 한 글자 포함 | `docs/DATA_MODEL.md`의 `name_ko`는 한국어 표시명 |
| 앞뒤 공백과 제어문자 금지 | 표시명 데이터 위생 |
| 한글이 없는 원천명과 동일 금지 | 영문명을 그대로 둔 미완료 행 차단 |
| 배치 내 중복 표시명 금지 | 사용자에게 같은 이름의 운동이 둘 이상 보이지 않게 함 |
| 의료 표현 금지: 진단, 치료, 처방, 재활 | `AGENTS.md` 제품 불변 규칙, `docs/DOMAIN_RULES.md` |

`T바 로우`처럼 한글과 함께 쓰는 로마자·숫자는 허용한다. KSPO 원천명은 이미 한국어이므로
원천명을 그대로 표시명으로 사용할 수 있다.

macOS에서 입력한 NFD 한글은 반려하지 않고 NFC로 정규화해 비교한다.

의료 표현 목록은 승인된 문서 문장에서 직접 가져온 최소 집합이다. 목록 확장, 장비 용어
통일안 및 표기 사전은 PM과 도메인 검토자의 승인을 받는다. 이 게이트는 표기 형식만
검사하며 번역 품질이나 운동 명칭의 정확성을 승인하지 않는다.

## 증적 행 검증

각 운동에는 다음 네 역할의 증적 행이 하나씩 있어야 한다.

| reviewer role | INCLUDE/MERGE에 필요한 상태 |
|---|---|
| DATA_OWNER | TECH_REVIEWED 또는 DOMAIN_APPROVED |
| BACKEND_REVIEWER | TECH_REVIEWED 또는 DOMAIN_APPROVED |
| PM_REVIEWER | TECH_REVIEWED 또는 DOMAIN_APPROVED |
| DOMAIN_REVIEWER | DOMAIN_APPROVED |

`DRAFT`가 아닌 증적은 다음 값을 모두 요구한다.

- reviewer reference: 이메일·실명이 아닌 내부 비식별 opaque code
- evidence reference: 문서, 이슈, PR 또는 검토 기록 참조
- reviewed_at: timezone이 포함된 ISO 8601 시각

사용자 건강 데이터, 검수자 이메일·실명, 인증정보는 결과 파일에 기록하지 않는다.

## 실행

wger 헬스장 트랙:

```powershell
python data/scripts/validate_wger_gym_review_results.py `
  "data/validation/review_batches/<gym-core-review-v0.2.0>" `
  "<mapping-results.csv>" `
  "<evidence-results.csv>"
```

KSPO 홈·맨몸 트랙:

```powershell
python data/scripts/validate_kspo_fitness100_review_results.py `
  "data/validation/review_batches/<training-video-review-batch-v0.2.0>" `
  "<mapping-results.csv>" `
  "<evidence-results.csv>"
```

검증 결과의 `review_complete_rows`는 구조와 증적이 완성된 INCLUDE/MERGE 행 수다.
`production_eligible`은 항상 `false`이며, 후속 normalized schema 및 seed 승격 게이트가
별도로 필요하다.
