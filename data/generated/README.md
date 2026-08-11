# Generated data

사람이 직접 수정하지 않는 DRAFT 파이프라인 산출물이다.

## 최신 산출물

| 디렉터리 | 내용 | 레코드 |
|---|---|---:|
| `exercise-catalog-seed-wger-mvp-v0.2.0` | wger 카탈로그 | 27 |
| `exercise-catalog-seed-kspo-mvp-v0.2.0` | KSPO 카탈로그 | 23 |
| `exercise-catalog-seed-wger-tranche3-v0.1.0` | wger 증분 카탈로그 | 3 |
| `exercise-catalog-seed-kspo-tranche3-v0.1.0` | KSPO 증분 카탈로그 | 3 |
| `exercise-safety-rules-mvp-v0.2.0` | 부위별 제외·주의 규칙 | 277 |
| `exercise-alternatives-mvp-v0.1.0` | 방향성 운동 대체 관계 | 224 |

이전 tranche 1 v0.1.0 산출물은 재현·비교를 위해 보존한다. 최신 카탈로그 매니페스트는
리뷰 배치, 매핑, 증적, 속성, taxonomy 입력 해시를 기록한다. 안전 규칙 매니페스트는
두 입력 시드의 매니페스트와 운동 파일 해시를 기록한다.

tranche 3 증분 카탈로그는 기존 50개를 덮어쓰지 않고 승인된 6개를 추가한다. 이후
안전 규칙과 대체 관계 생성에는 기존 시드 2개와 증분 시드 2개를 함께 입력한다.

`DOMAIN_APPROVED`는 생성기 호환 상태다. 실제 검토 방법은 `AGENT_ONLY`, 해석은
`PIPELINE_COMPATIBILITY_ONLY`, 운영 가능 여부는 `production_eligible=false`다.
DB 적재나 사용자 노출용으로 사용하지 않는다.

## 검증

```powershell
python data/scripts/build_exercise_catalog_seed.py verify `
  data/generated/exercise-catalog-seed-wger-mvp-v0.2.0
python data/scripts/build_exercise_catalog_seed.py verify `
  data/generated/exercise-catalog-seed-kspo-mvp-v0.2.0
python data/scripts/build_tranche_3_catalog_seed.py verify
python data/scripts/build_exercise_safety_rules.py verify `
  data/generated/exercise-safety-rules-mvp-v0.2.0
python data/scripts/build_exercise_alternatives.py verify `
  data/generated/exercise-alternatives-mvp-v0.1.0
```
