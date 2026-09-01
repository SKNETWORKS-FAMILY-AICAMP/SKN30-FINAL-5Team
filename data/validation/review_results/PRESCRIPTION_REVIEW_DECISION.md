# 처방·목표 태그 검토 결정 (2026-08-20)

상태: `APPROVED_FOR_PROMOTION`
검토 방법: `AGENT_ONLY` (개발 리드 위임)
generated artifact production eligible: `false`
runtime approval: `MERGED-MVP-20260820-PM-DOMAIN-APPROVAL`

## 왜 이 데이터가 필요한가

`docs/DATA_MODEL.md` 6.3.2의 `exercise_goal_tag_links`와
`exercise_prescription_profiles`는 루틴 생성의 필수 입력이다.
`RoutineRepository.get_creation_context`가 두 테이블을 inner join하므로 이 행이 없으면
카탈로그를 승인하고 활성화해도 후보가 0건이고 루틴이 만들어지지 않는다.

검토 배치와 속성 시트는 운동별 기본 수행시간·휴식만 담고 있고 목표 태그, 단계
(`WARMUP`/`MAIN`/`COOLDOWN`), 목표별 세트·반복 처방은 담고 있지 않았다. 그래서 이
검토 산출물을 새로 만들었다.

## 위임과 그 한계

tranche 1과 같은 방식이다. 개발 리드가 데이터 파트 총괄 권한으로 도메인 검토자 역할을
AI 에이전트에 위임했고, 그 사실을 여기 남긴다.

- `reviewer_reference`는 `AGENT-DOMAIN-REVIEW-PRESCRIPTION-V1`이다.
- 이 값은 외부 운동·건강 전문가의 검수를 뜻하지 않는다.
- 프로덕션 승격 게이트에서 전문가 검수 필요 여부를 다시 판단해야 한다.
- 산출물은 `production_eligible=false`인 DRAFT다.

## 작성 원칙

`docs/DATA_MODEL.md` 6.3.2는 **운동 이름이나 training type에서 목표·처방을 추론하지
말라**고 규정한다. 따라서 값은 규칙으로 생성하지 않고 운동별로 직접 작성했다. 작성한
표는 `scripts/prescription_review_authoring.py`의 `AUTHORED`에 있고 결과는
`prescription_results.csv`다.

작성 시 지킨 제약은 다음과 같다.

- 목표는 현재 배포 승인 목록에 있는 `GENERAL_FITNESS` 하나, 경험 수준은 `BEGINNER`
  하나다. 승인되지 않은 코드는 만들지 않았다.
- `CORE`는 목표를 실제로 담는 다관절 동작에만 부여했다. 솔버가 `CORE`가 없는 본운동
  조합을 버리기 때문에 홈·헬스장 각 트랙에 `CORE`가 남도록 확인했다.
- 보조·단순 동작은 `SUPPORT`, 부가 동작은 `OPTIONAL`로 두었다.
- 가동성 4종은 준비운동과 마무리에 모두 배정했다. 헬스장 트랙의 준비·마무리 후보가
  3종뿐이라 한 종목만으로도, 두 종목을 합쳐서도 시간 창을 만들 수 있게 값을 나눴다.
- 반복 기반 종목은 `reps`, 시간 기반 종목은 `work_seconds_per_set`만 채웠다.
  `exercise_prescription_profiles`의 `ck_..._timing` 제약이 둘 중 하나만 허용한다.

## 시간 구조 검증

`backend/app/modules/routines/service.py`의 `_select_exact_plan`은 계획 시간을 정확히
맞춘다. 제약은 준비운동 총합 60~180초, 마무리 총합 45~120초, 본운동에 `CORE` 최소 1종,
그리고 `setup = target - warmup - main - cooldown`이 0~60초다.

작성한 처방으로 온보딩이 제공하는 20·30·40·50분과 홈·헬스장 조합 여덟 가지 모두에서
정확한 해가 존재하는 것을 확인했다. 예를 들어 홈 50분은 준비 75초, 본운동 2754초,
마무리 120초, setup 51초로 3000초를 맞춘다.

홈 트랙은 처음 작성한 값으로 50분 목표에 본운동 상한이 582초 모자랐다. 홈에는
트레드밀 같은 장시간 유산소 종목이 없기 때문이다. 홈 보조·선택 종목 10종을 2세트에서
3세트로 올려 해결했다.

## 범위와 공백

- 처방은 `beginner_suitable=true`인 32종에만 작성했다. 루틴 조회가
  `beginner_suitable`을 걸러내므로 나머지 24종의 처방은 사용되지 않는 데이터가 된다.
- 실외 트랙은 준비운동·마무리 후보가 없어 어떤 시간에서도 해가 없다. 현재 온보딩이
  장소로 집과 헬스장만 제공하므로 사용자 영향은 없다. 실외를 노출하려면 카탈로그
  콘텐츠를 먼저 늘려야 한다.
- 위 시간 검증은 사용자가 해당 운동의 장비를 보유했다고 선언한 경우를 전제한다.
  장소별 기본 보유 장비와 온보딩 장비 선택지는 이 검토의 범위가 아니며 별도 이슈로
  다룬다.
- 칼로리, MET, RPE는 작성하지 않았다. `data/AGENTS.md`가 임의 값 사용을 금지한다.

## 재현

```powershell
python data/scripts/prescription_review_authoring.py write `
  --out data/validation/review_results/prescription_results.csv

python data/scripts/validate_exercise_prescription_review_results.py `
  data/generated/exercise-catalog-seed-merged-mvp-v0.4.0 `
  data/validation/review_results/prescription_results.csv

python data/scripts/build_exercise_prescriptions.py build `
  data/generated/exercise-catalog-seed-merged-mvp-v0.4.0 `
  data/validation/review_results/prescription_results.csv `
  --version-code merged-mvp-v0.1.0
```

## 승인 범위

2026-08-20에 개발 리드, PM, 도메인 검수 역할의 승인 증적을
`MERGED-MVP-20260820-PM-DOMAIN-APPROVAL`로 고정했다. 승인은 아래 네 값이 모두
일치할 때만 적용된다.

- 처방 산출물 `merged-mvp-v0.1.0`
- manifest SHA-256 `0ff5bf451345a57b6152cacc6d90e4aeb3cc9da5283093b2863ffbcd8af87273`
- goal tag 32건
- prescription profile 36건

generated manifest는 재현 가능한 DRAFT라는 의미로 계속
`production_eligible=false`를 유지한다. backend 승인 registry와 승격 migration이 위
version/hash/count를 다시 검사한 뒤 runtime 승인 metadata를 기록한다. 값이 하나라도
달라지면 새 승인이 필요하다.
