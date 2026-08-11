# Generated data

검증·승인된 애플리케이션 seed 산출물을 둡니다. 사람이 직접 수정하지 않고 source와 pipeline version을 기록합니다.

## 현재 산출물

| 디렉터리 | 트랙 | 운동 수 |
|---|---|---:|
| `exercise-catalog-seed-wger-tranche1-v0.1.0` | wger 헬스장 | 14 |
| `exercise-catalog-seed-kspo-tranche1-v0.1.0` | KSPO 홈·맨몸 | 10 |

각 디렉터리는 `exercises.jsonl`과 `seed_manifest.json`으로 구성되며, manifest는 원본
review batch와 taxonomy registry의 SHA-256을 기록합니다.

## production_eligible은 false입니다

두 seed 모두 `review.production_eligible`이 `false`이고 `verify` 명령이 이 값을
강제합니다. **DB에 적재해 개발을 진행하기 위한 DRAFT 카탈로그이며 사용자에게 내보낼 수
있는 상태가 아닙니다.**

`review_status_code`가 `DOMAIN_APPROVED`인 것은 파이프라인 검토 게이트를 통과했다는
뜻입니다. tranche 1의 검토는 AI 에이전트가 개발 리드 위임으로 수행했으며 자격을 갖춘
운동·재활 전문가의 검수가 아닙니다. 범위와 한계는
[review_results/TRANCHE1_REVIEW_DECISION.md](../validation/review_results/TRANCHE1_REVIEW_DECISION.md)에
있습니다.

## 재생성

```powershell
python data/scripts/build_exercise_catalog_seed.py verify `
  data/generated/exercise-catalog-seed-wger-tranche1-v0.1.0
```

`build`는 같은 이름의 디렉터리가 이미 있으면 실패합니다. 재생성하려면 기존 디렉터리를
지우거나 `--version-code`를 올립니다.
