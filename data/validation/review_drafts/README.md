# 검토 초안 (AI draft)

상태: `DRAFT`
프로덕션 사용 가능: `false`

## 이 폴더가 무엇인가

도메인 검토자가 빈 시트를 처음부터 채우지 않도록 기계가 미리 채운 초안입니다.
`build_review_tranche_draft.py`가 `normalized/review_tranche_1.draft.json`을 읽어
생성하며, 재실행하면 같은 결과가 나옵니다.

**이 파일들은 승인 데이터가 아닙니다.** 모든 승인 열은 `PENDING`이고 `review_status`는
`DRAFT`, `production_eligible`은 `false`입니다. 검토자가 승인 열을 바꾸기 전에는
`build_exercise_catalog_seed.py build`가 계속 실패합니다.

## 1차 트랜치 구성

검토자 1회 세션으로 끝낼 수 있는 규모로 나눴습니다. MVP 카탈로그 목표 규모를 바꾸는
것이 아니라 검토 순서를 나눈 것입니다.

| 트랙 | 배치 전체 | 초안 작성 | 그대로 `PENDING` |
|---|---:|---:|---:|
| wger 헬스장 | 60 | 14 | 46 |
| KSPO 홈 | 50 | 10 | 40 |

무릎 주도 5개를 제외해도 고관절 주도 4개와 상체 8개가 남도록 구성했습니다. 골든 시나리오
"무릎 불편 시 무릎 부하 제외"가 실제로 검증됩니다.

## 기계가 채운 값과 비워 둔 값

`draft_source` 열이 `AI_DRAFT_...`인 행은 기계가 채운 행입니다. 승인 전에 반드시
확인해야 합니다.

채운 값: 정규화 ID, 한국어 표시명, 운동 유형·초점·패턴, 장비, 장소, 난이도,
수행 방식과 시간, 세트 간 휴식, 회복 가능 여부, 전환 시간(정책값 15초)

**의도적으로 비워 둔 값**

| 필드 | 이유 |
|---|---|
| `primary_body_area_codes`, `secondary_body_area_codes` | body_area는 사용 근육이 아니라 관절·부위 부하다. 어떤 원천도 제공하지 않으므로 근육에서 추론하지 않는다. 안전 제외 규칙이 이 값에 걸린다. |
| `instruction_summary_ko`, `form_cues_ko` | 자세 문구는 사람이 작성한다. wger 영문 설명은 CC-BY-SA 전파 조건 확인이 필요하다. |
| `instruction_content_version` | 위 문구가 작성된 뒤 부여한다. |

안전 제외 규칙과 대체 관계는 이 폴더에서 다루지 않습니다. 별도 검수 데이터이며 전문가가
작성합니다.

## 검토자 작업 순서

1. 두 CSV를 사본으로 복사한다.
2. `draft_source`가 표시된 행의 값을 확인하고 필요하면 고친다.
3. 비워 둔 body_area와 자세 문구를 작성한다.
4. 판단이 끝난 행만 `review_decision`과 승인 상태를 바꾼다.
5. 증적 시트에 역할별 `reviewer_reference`, `evidence_reference`, `reviewed_at`을 적는다.
6. `build_exercise_catalog_seed.py readiness`로 남은 항목을 확인한다.

## 재생성

```powershell
python data/scripts/build_review_tranche_draft.py wger `
  data/normalized/review_tranche_1.draft.json `
  --mapping-out data/validation/review_drafts/wger_tranche1_mapping_draft.csv `
  --attributes-out data/validation/review_drafts/wger_tranche1_attributes_draft.csv
```
