# 검토 결과 작성 폴더

**여기 있는 파일을 직접 편집하세요.** `review_drafts/`는 생성기 출력물이라 재실행하면
덮어써지지만, 이 폴더는 도구가 건드리지 않습니다.

## 진행 상태 (2026-08-11)

tranche 1의 24종은 검토가 끝났고 seed까지 생성했습니다. 결정 내용과 한계는
[TRANCHE1_REVIEW_DECISION.md](TRANCHE1_REVIEW_DECISION.md)에 있습니다.

| 트랙 | 완료 | 남은 `PENDING` |
|---|---:|---:|
| wger | 14 | 46 |
| KSPO | 10 | 40 |

아래 작성 방법은 tranche 2 이후에 그대로 적용됩니다.

### 부위 판정 정의

tranche 1에서 확정한 구분입니다. `exercise_safety_rules`가 이 구분에 의존하므로 같은
기준을 유지하세요.

| 값 | 의미 | 안전 규칙에서의 용도 |
|---|---|---|
| `PRIMARY` | 이 동작의 부하를 직접 받는 관절·부위 | 해당 부위 불편 시 **제외** 후보 |
| `SECONDARY` | 자세 유지나 보조 동작으로 부하를 받는 부위 | 해당 부위 불편 시 **주의·대체** 후보 |

## 어떤 파일에 무엇을 쓰는가

| 파일 | 작성 내용 | 행 수 |
|---|---|---:|
| `wger_attributes.csv` | **부위 매핑 + 자세 문구** | 14 |
| `kspo_attributes.csv` | **부위 매핑 + 자세 문구** | 10 |
| `wger_mapping_results.csv` | 포함 여부와 승인 상태 | 60 (초안 14) |
| `kspo_mapping_results.csv` | 포함 여부와 승인 상태 | 50 (초안 10) |
| `wger_evidence_results.csv` | 역할별 검수 증적 | 240 |
| `kspo_evidence_results.csv` | 역할별 검수 증적 | 200 |

## 1. attributes CSV — 도메인 검토자의 핵심 작업

`draft_source`가 `AI_DRAFT_...`인 행은 기계가 채운 초안입니다. 확인하고 필요하면 고치세요.

**반드시 직접 작성해야 하는 5개 열**

| 열 | 작성 방법 |
|---|---|
| `primary_body_area_codes` | 이 운동이 주로 부하를 주는 부위. 여러 개면 `\|`로 구분 |
| `secondary_body_area_codes` | 보조적으로 부하가 걸리는 부위. 없으면 비움 |
| `instruction_summary_ko` | 블록에서 펼쳐볼 수행 설명 |
| `form_cues_ko` | 핵심 자세 포인트 |
| `instruction_content_version` | 위 문구의 버전. 예: `1.0.0` |

`body_area_code`는 `docs/DOMAIN_RULES.md` 3.2절의 13개만 사용합니다.

```
NECK, SHOULDER, ELBOW, WRIST_HAND, UPPER_BACK, LOWER_BACK, HIP,
KNEE, ANKLE_FOOT, CHEST, ABDOMEN, GENERALIZED, OTHER
```

**주의:** 이 값은 사용 근육이 아니라 **부하가 걸리는 관절·부위**입니다. 예를 들어
레그프레스는 대퇴사두를 쓰지만 부하 부위는 무릎과 엉덩관절입니다. 사용자가 불편하다고
고른 부위와 이 값이 맞물려 운동 제외가 결정되므로, 근육명이 아니라 부위로 적어주세요.

작성이 끝난 행은 `attribute_status`를 `DOMAIN_APPROVED`로 바꿉니다.

## 2. mapping CSV — 포함 여부 판단

초안이 채워진 행만 검토하고, 나머지는 `PENDING`으로 두면 됩니다.

- `review_decision`: `INCLUDE`, `MERGE`, `EXCLUDE` 중 하나. `EXCLUDE`는 `reviewer_notes`에 사유 필수
- `review_beginner_suitability`: `YES`, `CONDITIONAL`, `NO`
- `review_execution_guidance_status`, `review_domain_safety_status`: `APPROVED` 또는 `REJECTED`
- wger는 `review_license_status`, KSPO는 `review_media_rights_status`
- `review_taxonomy_code`: 승인된 movement pattern 코드(대문자)만 허용

원천 식별자·이름 등 나머지 열은 바꾸면 검증에 실패합니다.

## 3. evidence CSV — 검수 증적

`INCLUDE`/`MERGE` 행은 네 역할의 증적이 모두 필요합니다.

| 역할 | 필요한 상태 |
|---|---|
| `DATA_OWNER`, `BACKEND_REVIEWER`, `PM_REVIEWER` | `TECH_REVIEWED` 이상 |
| `DOMAIN_REVIEWER` | `DOMAIN_APPROVED` |

`DRAFT`가 아닌 행은 `reviewer_reference`(이메일·실명이 아닌 내부 비식별 코드),
`evidence_reference`, timezone이 포함된 `reviewed_at`이 모두 필요합니다.

## 4. 진행 상황 확인

언제든 실행해서 남은 항목을 볼 수 있습니다. 실패시키지 않고 보고만 합니다.

```powershell
python data/scripts/build_exercise_catalog_seed.py readiness wger `
  "data/validation/review_batches/20260810T063833Z-wger-exercise-catalog-profile-v0.1.0-gym-core-review-v0.2.0" `
  data/validation/review_results/wger_mapping_results.csv `
  data/validation/review_results/wger_evidence_results.csv `
  --attributes data/validation/review_results/wger_attributes.csv `
  --taxonomy-registry data/normalized/exercise_taxonomy_codes.json
```

모두 채워지면 `build`로 seed를 생성합니다. 조건이 하나라도 어긋나면 아무것도 만들지
않고 실패합니다.
