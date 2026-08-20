# FEATURE_SPEC.md

운동 수행 여부 예측 ML의 **피처 계약**이다. 컬럼명은 이 문서를 단일 기준으로 삼는다.
임의로 만들거나 바꾸지 않는다. 변경이 필요하면 3인 합의 후 이 문서를 먼저 고친다.

**이 문서는 실제 데이터 파일을 확인해 작성했다.** 추측한 컬럼은 없다.

- Track A는 이 스펙대로 데이터셋을 생성한다.
- Track B는 `block` 태그로 ablation을 구성한다. 컬럼을 직접 나열하지 않는다.
- Track C는 `role=segment` 컬럼으로 세그먼트 분석을 한다.

---

## 1. 원본 데이터 실측

`ml/data/Whoop Fitness Dataset/whoop_fitness_dataset_100k.csv`

| 항목 | 실측값 |
|---|---|
| 행 수 | 100,000 |
| 사용자 수 | 286 |
| 기간 | 2023-01-01 ~ 2024-02-03 (약 13개월) |
| 사용자당 행 수 | 최소 137 / 중앙값 351 / 최대 399 |
| 컬럼 수 | 39 |
| 타깃 기저율 | `workout_completed` = 1 이 **54.01%** |
| 결측 | **`workout_time_of_day` 45,990건이 유일** (= 미수행일 수와 정확히 일치) |

### 1.1 확인된 라벨 구조

| 지표 | 값 |
|---|---|
| lag-1 상관 | **0.155** |
| P(수행=1 \| 전일 수행) | **0.612** |
| P(수행=1 \| 전일 미수행) | **0.457** |
| 평일 수행률 | 화 0.591 / 금 0.591 / 수 0.590 / 목 0.588 / 월 0.586 |
| 주말 수행률 | **토 0.418 / 일 0.417** |

자기상관은 존재하나 지배적이지 않다(격차 약 15%p). **요일 효과가 훨씬 크다**(평일-주말 약 17%p).
`A0` 다수 클래스 baseline의 관측 정확도는 **0.5401**이다.

> 요일 효과는 합성 생성기의 파라미터일 가능성이 높다. 한국 사용자의 실제 패턴은 반대일 수 있다.
> 결과서에서 이를 실사용자 행동 근거로 쓰지 않는다.

---

## 2. 설계 원칙: 서비스 전이 가능성

피처를 서비스의 실제 도메인 어휘(`docs/DATA_MODEL.md` 7.7 `wearable_summaries`)에 맞췄다.
자체 데이터가 쌓였을 때 **같은 파이프라인을 재사용**하기 위해서다.

### 2.1 서비스 수집 항목과의 대응

| 서비스 `wearable_summaries` | Whoop 원본 (전일 이동) | 상태 |
|---|---|---|
| `sleep_minutes` | `sleep_hours` × 60 | ✅ 대응 |
| `resting_heart_rate_trend` | `resting_heart_rate` → 3값 코드 | ✅ 대응 (5절) |
| `last_workout_duration_minutes` | `activity_duration_min` | ✅ 대응 |
| `last_workout_type_code` | `activity_type` | ✅ 대응 |
| `active_calories_burned` | `activity_calories` | ✅ 대응 |
| `average_heart_rate` | `avg_heart_rate` | ✅ 대응 |
| `steps` | — | ❌ **원본에 없음** |
| `active_minutes` | — | ❌ **원본에 없음** |

`steps`와 `active_minutes`는 Whoop 데이터에 존재하지 않는다. `A3`에서 제외하고 결과서 11절에 기록한다.

### 2.2 서비스가 수집하지 않는 항목

`hrv`, `recovery_score`, `day_strain`, 수면 세부(효율·단계·각성), `respiratory_rate`,
`skin_temp_deviation`은 **서비스 `wearable_summaries`에 대응 컬럼이 없다.**

→ `A5` 블록으로 분리한다. **결과가 좋아도 제품 설계 근거로 쓰지 않는다.**
결과서에서 실제 설계 근거로 쓸 수 있는 것은 `A4`까지다.

### 2.3 서비스에는 있으나 원본에 없는 것

| 서비스 컬럼 | 상태 |
|---|---|
| `daily_contexts.fatigue_level_code` (LOW/MODERATE/HIGH) | 대응 없음. **재학습 시 추가할 핵심 피처** |
| `daily_contexts.requested_duration_minutes` | 대응 없음 |
| `daily_context_discomforts` | 대응 없음. 안전 영역이며 ML 입력 대상 아님 |

---

## 3. 제외 컬럼과 근거

### 3.1 누수 — 당일 결과성 값 (14개)

운동 수행 후 생성되거나 타깃을 직접 노출한다. **당일 값으로는 절대 사용하지 않는다.**
단, 전일로 이동(`shift(1)`)한 값은 정당한 피처이며 4절에서 사용한다.

```text
activity_type              당일. 미수행일에 "Rest Day" -> 타깃 직접 노출
activity_duration_min      당일
activity_strain            당일
activity_calories          당일
avg_heart_rate             당일 운동 평균 심박
max_heart_rate             당일 운동 최대 심박
hr_zone_1_min ~ hr_zone_5_min   당일 심박구간별 운동시간 (5개)
workout_time_of_day        당일. 미수행일에 결측 -> 타깃 직접 노출
```

**추가로 발견된 누수 (초기 목록에 없었음):**

```text
day_strain         당일 전체 부하. 운동을 포함해 계산됨
                   미수행일 평균 9.6 vs 수행일 10.2
calories_burned    당일 전체 칼로리. 운동을 포함해 계산됨
                   미수행일 평균 3233.8 vs 수행일 3331.6
```

두 컬럼은 이름에 `activity`가 없어 무해해 보이지만 **당일 운동 결과가 섞여 있다.**
차이가 작아도 모델은 이용한다. 당일 값으로 쓰지 않는다.

### 3.2 누수 — 전기간 상수 baseline

```text
hrv_baseline       사용자당 고유값 1개 (전기간 상수)
rhr_baseline       사용자당 고유값 1개 (전기간 상수)
```

**실측 확인 결과 두 컬럼은 사용자별로 값이 하나뿐이다.** 즉 전체 기간(미래 포함)으로 계산된
전역 평균이며, 롤링 기준선이 아니다. 사용하면 두 가지 문제가 생긴다.

1. **미래 정보 유입** — 학습 구간에서 평가 구간의 값이 반영된 상수를 본다
2. **사용자 지문** — 시간 기반 분할에서 사용자 식별자로 작동한다

→ **사용하지 않는다.** 개인 기준선이 필요하면 4.5절처럼 **직접 인과적으로 계산**한다.

### 3.3 정책상 제외

| 컬럼 | 근거 |
|---|---|
| `age` | `docs/DOMAIN_RULES.md` 8절 — **만 나이는 에이전트 입력에 포함하지 않는다.** 제품에서 못 쓰는 피처는 학습에도 넣지 않는다 |
| `gender` | 서비스 `user_profiles`에 대응 필드 없음. 전이 불가 |
| `primary_sport` | 서비스 `primary_goal_code`와 의미가 다름. 값 8종, 전이 어려움 |
| `weight_kg`, `height_cm` | 사용자당 상수. 시간 기반 분할에서 사용자 지문으로 작동. 수행 여부 예측에 기여 근거 없음 |

### 3.4 무효 컬럼

```text
sleep_performance   전 행이 100.0 (평균 100.0, 표준편차 0.0)
```

분산이 0이므로 정보가 없다. 제외한다.

---

## 4. 컬럼 명세

`role`: `identifier` | `feature` | `segment` | `target`
`identifier`와 `segment`는 **모델 입력에서 제외**한다.
단, `experience_level_code`는 `A1` 피처이면서 세그먼트 분석에도 쓰는 **이중 용도**다.
`A1`이 포함된 ablation에서는 모델 입력으로 사용하고, 예측 결과에도 세그먼트용으로 유지한다.

모든 전일 피처는 `df.sort_values(["user_id","local_date"]).groupby("user_id").shift(1)`로 만든다.

### 4.1 식별자 (block `meta`)

| column_name | dtype | role | derivation |
|---|---|---|---|
| `user_id` | string | identifier | 원본 `user_id` |
| `local_date` | date | identifier | 원본 `date`. 서비스 `local_date` 명칭에 맞춤 |

### 4.2 타깃 (block `target`)

| column_name | dtype | role | derivation |
|---|---|---|---|
| `workout_completed` | int8 | target | 원본 그대로. 1 = 운동 기록 있음 |

> **한계**: 서비스 공식 수행 상태는 `COMPLETED`/`PARTIAL`/`NOT_COMPLETED` 3값이다
> (`docs/DOMAIN_RULES.md` 476행). 이 타깃은 **활동 발생 여부**이며 `PARTIAL`을 표현하지 못한다.

### 4.3 `A1` — 프로필·달력

| column_name | dtype | role | derivation |
|---|---|---|---|
| `experience_level_code` | category | feature | `fitness_level` 매핑 (6절) |
| `day_of_week` | int8 | feature | 원본은 `"Monday"` 등 **문자열**. 0=월 … 6=일로 변환 |
| `is_weekend` | bool | feature | `day_of_week >= 5`. 실측상 가장 강한 단일 신호 |

### 4.4 `A2` — 운동 이력 (앱이 직접 기록, 전이 가능성 최상)

모두 **과거 라벨에서 인과적으로** 파생한다. 사용자별 시간순 누적이며 미래 값을 포함하지 않는다.

| column_name | dtype | role | missing_policy | derivation |
|---|---|---|---|---|
| `workout_completed_prev_day` | int8 | feature | 첫날 0 (`history_days`로 구분) | `shift(1)` |
| `workout_count_7d` | int8 | feature | 관측 구간만 집계 | 직전 7일 합 (당일 제외) |
| `workout_count_28d` | int8 | feature | 관측 구간만 집계 | 직전 28일 합 (당일 제외) |
| `completion_rate_7d` | float32 | feature | 관측일수로 나눔 | `workout_count_7d / 관측일수` |
| `completion_rate_28d` | float32 | feature | 관측일수로 나눔 | `workout_count_28d / 관측일수` |
| `days_since_last_workout` | int16 | feature | 이력 없으면 `-1` | 마지막 수행일로부터 경과일 |
| `consecutive_workout_days` | int16 | feature | 0 | 당일 직전까지 연속 수행일 |
| `consecutive_non_workout_days` | int16 | feature | 0 | 당일 직전까지 연속 미수행일 |
| `is_return_mode_candidate` | bool | feature | false | `days_since_last_workout >= 14`. **`docs/DOMAIN_RULES.md` 7절 `RETURN_MODE_COMPLETION_GAP_DAYS=14`와 동일 기준** |

> `is_return_mode_candidate`는 제품의 복귀 모드 임계값을 그대로 쓴다.
> 단, 제품의 복귀 모드는 **공식 `COMPLETED` 세션** 기준이므로 정의가 완전히 같지는 않다.

### 4.5 `A3` — 전일 웨어러블 요약 (서비스 수집 가능)

전부 전일 값이며, 서비스 `wearable_summaries`에 대응 컬럼이 존재한다.

| column_name | dtype | role | 서비스 대응 | derivation |
|---|---|---|---|---|
| `sleep_minutes_prev_day` | float32 | feature | `sleep_minutes` | `sleep_hours × 60` → `shift(1)` |
| `resting_hr_prev_day` | float32 | feature | — | `resting_heart_rate` → `shift(1)` |
| `resting_hr_trend_code_prev_day` | category | feature | `resting_heart_rate_trend` | 5절 규칙 |
| `last_workout_duration_min_prev_day` | float32 | feature | `last_workout_duration_minutes` | `activity_duration_min` → `shift(1)` |
| `last_workout_type_code_prev_day` | category | feature | `last_workout_type_code` | `activity_type` → `shift(1)`. `Rest Day`는 `NONE`으로 코드화 |
| `last_workout_calories_prev_day` | float32 | feature | `active_calories_burned` | `activity_calories` → `shift(1)` |
| `last_workout_avg_hr_prev_day` | float32 | feature | `average_heart_rate` | `avg_heart_rate` → `shift(1)` |

> 이 컬럼들은 **전일** 값이므로 누수가 아니다. 당일 값만 3.1절에서 금지된다.

### 4.6 `A4` — 개인 기준선 대비 변화 (직접 계산)

`hrv_baseline`·`rhr_baseline`을 쓰지 않고 **직접 인과적으로** 계산한다.
직전 28일 개인 평균이며 당일과 미래를 포함하지 않는다.

| column_name | dtype | role | derivation |
|---|---|---|---|
| `sleep_minutes_delta_28d` | float32 | feature | `sleep_minutes_prev_day` − 직전 28일 개인 평균 |
| `resting_hr_delta_28d` | float32 | feature | `resting_hr_prev_day` − 직전 28일 개인 평균 |

### 4.7 `A5` — 서비스 미수집 (탐색 전용, **전이 불가**)

**서비스 `wearable_summaries`에 대응 컬럼이 없다.** 제품 설계 근거로 쓰지 않는다.

| column_name | dtype | derivation |
|---|---|---|
| `hrv_prev_day` | float32 | `hrv` → `shift(1)` |
| `hrv_delta_28d` | float32 | `hrv_prev_day` − 직전 28일 개인 평균 |
| `recovery_score_prev_day` | float32 | `shift(1)` |
| `day_strain_prev_day` | float32 | `shift(1)` |
| `calories_burned_prev_day` | float32 | `shift(1)` |
| `sleep_efficiency_prev_day` | float32 | `shift(1)` |
| `light_sleep_hours_prev_day` | float32 | `shift(1)` |
| `rem_sleep_hours_prev_day` | float32 | `shift(1)` |
| `deep_sleep_hours_prev_day` | float32 | `shift(1)` |
| `wake_ups_prev_day` | int16 | `shift(1)` |
| `time_to_fall_asleep_min_prev_day` | float32 | `shift(1)` |
| `respiratory_rate_prev_day` | float32 | `shift(1)` |
| `skin_temp_deviation_prev_day` | float32 | `shift(1)` |

### 4.8 세그먼트 분석 컬럼

**예측 결과 파일에 반드시 포함**한다.
`history_days`와 `history_bucket`은 block `meta`이며 모델 입력에서 제외한다.
`experience_level_code`는 `A1` 피처로 입력하면서 동시에 세그먼트 분석에 사용한다.

| column_name | dtype | role | derivation |
|---|---|---|---|
| `history_days` | int16 | segment | 해당 행 시점까지 관측된 일수 |
| `history_bucket` | category | segment | `0-7` / `8-28` / `29+` |
| `experience_level_code` | category | feature | 4.3절의 `A1` 피처이며 세그먼트 분석에도 사용 |

> **가용성 플래그는 만들지 않는다.** 실측 결과 이 데이터셋에는 웨어러블 결측이 **전혀 없다**
> (유일한 결측은 타깃 누수 컬럼인 `workout_time_of_day`). 플래그를 만들면 전 행이 `True`인
> 분산 0 컬럼이 된다.
>
> 따라서 **"웨어러블 유무" 세그먼트 분석은 이 데이터로 불가능하다.**
> 같은 제품 질문은 **`A2` vs `A3` ablation이 더 정확하게 답한다** —
> 웨어러블 피처를 뺀 모델과 넣은 모델의 성능 차이가 곧 "웨어러블 없는 사용자의 손실"이다.
> 이 대체 사실을 결과서 11절에 기록한다.

---

## 5. `resting_hr_trend_code_prev_day` 산출 규칙

서비스는 안정시 심박을 **3값 코드**로 정규화해 저장한다. 연속값만 쓰면 전이되지 않으므로
동일 형태의 파생 피처를 함께 만든다.

```text
resting_hr_delta_28d >=  +2.0 bpm  ->  UPWARD
resting_hr_delta_28d <=  -2.0 bpm  ->  DOWNWARD
그 외                              ->  STABLE
```

- 임계값 `2.0 bpm`은 **ML 임시 규칙 v0.1**이며 의학적 기준이 아니다.
- 서버 정규화 규칙(`normalization_version`)이 확정되면 교체한다.
- 임계값과 버전을 결과서 4절에 기재한다.

---

## 6. `experience_level_code` 매핑

원본 `fitness_level`의 실측 고유값은 **4종**이다: `Beginner`, `Intermediate`, `Advanced`, `Elite`.

| Whoop `fitness_level` | `experience_level_code` |
|---|---|
| `Beginner` | `BEGINNER` |
| `Intermediate` | `INTERMEDIATE` |
| `Advanced` | `ADVANCED` |
| `Elite` | `ADVANCED` |

`Elite`를 `ADVANCED`로 병합한다. 서비스는 운동 초보자·복귀 사용자가 대상이며
`Elite` 구간의 별도 처리가 제품에 없다. **병합 사실을 결과서 4절에 기재한다.**

> 서비스 `user_profiles.experience_level_code`의 확정 코드값이 3종과 다르면 이 표를 갱신한다.

---

## 7. Ablation 블록 요약

| ID | 포함 블록 | 전이 가능성 | 목적 |
|---|---|---|---|
| `A0` | 없음 (다수 클래스) | — | 관측 baseline 정확도 0.5401 |
| `A1` | `A1` | 높음 | 콜드스타트 구간 상한 |
| `A2` | `A1`+`A2` | **최상** | 앱이 직접 기록하는 정보만 |
| `A3` | `A1`+`A2`+`A3` | 높음 | 서비스 수집 가능 웨어러블 추가 효과 |
| `A4` | `A1`+`A2`+`A3`+`A4` | 높음 | 개인 기준선 추가 효과 |
| `A5` | 전체 | **없음** | 탐색 전용. 제품 근거로 쓰지 않음 |
| `A2-lag1` | `workout_completed_prev_day`, `day_of_week` | — | 자기상관 참조선 |

**핵심 비교는 `A2` → `A3`이다.** 웨어러블이 앱 기록 대비 추가 정보를 주는지가
서비스 설계에 직결되며, 4.8절에 따라 "웨어러블 유무" 질문도 이 비교가 대신 답한다.

`A2-lag1`도 중요하다. 실측 lag-1 상관이 0.155에 불과하므로,
**전체 모델이 이 참조선을 크게 넘지 못하면 나머지 피처는 기여가 없다는 뜻**이다.

---

## 8. 예측 결과 스키마 (Track B → Track C)

`ml/outputs/predictions/predictions_{split_type}_{ablation_id}_{model_id}.parquet`

| column | dtype | 설명 |
|---|---|---|
| `user_id` | string | |
| `local_date` | date | |
| `split_type` | category | `time` \| `user` |
| `split_part` | category | `train` \| `val` \| `test` |
| `ablation_id` | category | `A0` … `A5`, `A2-lag1` |
| `model_id` | category | `majority` \| `logreg` \| `rf` \| `histgb` |
| `y_true` | int8 | 0 / 1 |
| `y_prob` | float32 | 0.0 ~ 1.0 |
| `history_days` | int16 | 세그먼트용 |
| `history_bucket` | category | 세그먼트용 |
| `experience_level_code` | category | 세그먼트용 |

**세그먼트 3개 컬럼이 반드시 포함돼야 한다.** 빠지면 Track B가 전체 실험을 다시 돌려야 한다.

`ml/outputs/experiments.csv`

| column | 설명 |
|---|---|
| `experiment_id` | 고유 ID |
| `split_type` | `time` \| `user` |
| `ablation_id` | |
| `model_id` | |
| `n_train`, `n_val`, `n_test` | 행 수 |
| `n_users_train`, `n_users_val`, `n_users_test` | **사용자 수.** 사용자 기반 분할의 일반화 주장 근거 |
| `hyperparams` | JSON 문자열 |
| `seed` | 고정 시드 |
| `git_commit` | 재현용 |
| `run_at` | ISO 8601 |
