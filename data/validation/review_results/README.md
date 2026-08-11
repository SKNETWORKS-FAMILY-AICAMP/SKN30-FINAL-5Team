# 검토 결과

2026-08-11 기준 리뷰 배치 110개를 모두 결정했다.

| 트랙 | 포함 | 제외 | 미결 | 속성 행 | 증적 행 |
|---|---:|---:|---:|---:|---:|
| wger | 27 | 33 | 0 | 27 | 240 |
| KSPO | 23 | 27 | 0 | 23 | 200 |
| 합계 | 50 | 60 | 0 | 50 | 440 |

## 파일

- `*_mapping_results.csv`: 포함·제외, stable code, 표시명, taxonomy, 검토 상태
- `*_evidence_results.csv`: 후보별 네 역할 검토 증적
- `*_attributes.csv`: 포함 운동의 시간·부위·장비·위치·실행 안내
- `TRANCHE1_REVIEW_DECISION.md`: 기존 24개 1차 검토 기록
- `../../normalized/review_tranche_2.agent.json`: 나머지 86개 검토 계획과 제외 사유
- `../../normalized/agent_review_policy.json`: 에이전트 단독 검토 정책과 한계

## 상태 해석

새 검토 결과의 실제 방법은 `AGENT_ONLY`다. CSV의 `DOMAIN_APPROVED`와
`TECH_REVIEWED`는 기존 validator와 seed generator가 요구하는 호환 상태 코드일 뿐,
외부 운동·의료 전문가의 승인을 뜻하지 않는다. 모든 행과 생성물은
`production_eligible=false`로 유지한다.

포함 행은 DATA_OWNER, BACKEND_REVIEWER, PM_REVIEWER의 `TECH_REVIEWED`와
DOMAIN_REVIEWER의 `DOMAIN_APPROVED` 증적을 모두 가져야 한다. 제외 행은 사유 코드와
한국어 설명을 `reviewer_notes`에 남긴다.

## 검증

```powershell
python data/scripts/validate_wger_gym_review_results.py `
  data/validation/review_batches/20260810T063833Z-wger-exercise-catalog-profile-v0.1.0-gym-core-review-v0.2.0 `
  data/validation/review_results/wger_mapping_results.csv `
  data/validation/review_results/wger_evidence_results.csv

python data/scripts/validate_kspo_fitness100_review_results.py `
  data/validation/review_batches/20260810T053458Z-training-video-profile-v0.2.0-review-batch-v0.2.0 `
  data/validation/review_results/kspo_mapping_results.csv `
  data/validation/review_results/kspo_evidence_results.csv
```
