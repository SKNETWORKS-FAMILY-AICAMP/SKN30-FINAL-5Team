# Model Card: A3 HistGradientBoosting

## 모델 개요

| 항목 | 내용 |
|---|---|
| 아티팩트 | `final_model_A3_histgb.joblib` |
| 형태 | sklearn `Pipeline` (`preprocessor` + `HistGradientBoostingClassifier`) |
| 용도 | Whoop 합성 데이터에서 전일까지의 정보로 해당 날짜의 운동 기록 존재 여부를 오프라인 분석 |
| 사용 가능 범위 | 오프라인 분석과 재현성 검증에 한정 |
| 개발 상태 | 분석 완료. 제품 런타임 사용 금지 |

## 학습 데이터

- 출처: [Whoop Fitness Dataset 100K](https://www.kaggle.com/datasets/likithagedipudi/whoop-fitness-dataset)
- 라이선스: CC0: Public Domain
- 성격: 합성 데이터셋. 실사용자 데이터가 아님
- 원본: 100,000행, 286명, 2023-01-01 ~ 2024-02-03, 39컬럼
- 재학습: 시간 분할 train + validation 94,618행, 286명
- 원본 SHA-256: `094fa329dd2bd886dd72bf2d5b615d5d901516c7a4f4a020d112e0a48de4dd1c`

## 타깃

`workout_completed = 1`은 해당 날짜에 운동 기록이 존재함을 뜻한다. 이 타깃은 제품의 공식 수행 상태를 직접 예측하지 않으며, `PARTIAL`이 소실되었다. 모델 출력은 제품의 공식 수행 상태를 대체하지 않는다.

## 입력 피처

피처 19개는 [FEATURE_SPEC.md](../docs/FEATURE_SPEC.md)의 A1 + A2 + A3 정의를 따른다.

| 블록 | 피처 |
|---|---|
| A1 | `experience_level_code`, `day_of_week`, `is_weekend` |
| A2 | `workout_completed_prev_day`, `workout_count_7d`, `workout_count_28d`, `completion_rate_7d`, `completion_rate_28d`, `days_since_last_workout`, `consecutive_workout_days`, `consecutive_non_workout_days`, `is_return_mode_candidate` |
| A3 | `sleep_minutes_prev_day`, `resting_hr_prev_day`, `resting_hr_trend_code_prev_day`, `last_workout_duration_min_prev_day`, `last_workout_type_code_prev_day`, `last_workout_calories_prev_day`, `last_workout_avg_hr_prev_day` |

제외: 당일 운동 결과성 컬럼·전기간 상수·정책상 제외 컬럼·식별자. `user_id`, `local_date`, `history_days`, `history_bucket`는 모델 입력이 아니다.

## 전처리와 하이퍼파라미터

- 범주형: 고유 범주를 정수로 인코딩하고 결측 토큰 사용
- 수치형: 학습 세트의 중앙값으로 대체
- Estimator: `HistGradientBoostingClassifier`
- 하이퍼파라미터: `learning_rate=0.1`, `max_iter=300`, `random_state=42`
- 판정 임계값: 0.5 (평가용이며 제품 의사결정 규칙이 아님)

## 분할·선정 근거

- 분할: 시간 기반 70/15/15
- 선정 지표: validation PR-AUC
- 최종 후보 제외: 서비스 미수집 피처 블록 `A5`
- 선정 증거: `time_A3_histgb`, validation PR-AUC 0.7643486950569605
- 재학습: 시간 train + validation 94,618행
- test: 동결 후보 이후 1회 평가. test 결과로 재선정하지 않음

## 성능

| 세트 | 표본 | Precision | Recall | F1 | ROC-AUC | PR-AUC | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|
| validation | 14,966 | 0.699037 | 0.651215 | 0.674279 | 0.728009 | 0.764349 | 0.208651 |
| test | 5,382 | 0.697824 | 0.670322 | 0.683797 | 0.726203 | 0.766122 | 0.209051 |

- test confusion matrix: TN 1,617 / FP 847 / FN 962 / TP 1,956
- test 경험 구간별 PR-AUC: BEGINNER 0.385304 / INTERMEDIATE 0.529322 / ADVANCED 0.852781
- 임계값 0.5에서 BEGINNER test 구간의 양성 판정이 0건이었다. 세그먼트 편차가 크므로 이 임계값을 제품에 사용하면 안 된다.

## 사용 금지

이 모델은 아래 목적에서 **사용하지 않는다.**

- 통증·이상 반응 판단
- 안전 veto 생성 또는 변경
- `REST` / `STOP_AND_SEEK_HELP` 결정
- 운동 강도·난이도 결정
- 사용자 요청 시간 단축
- 웨어러블만으로 계획 변경
- 운동 완료 상태 자동 판정
- 미수행 가능성을 근거로 한 압박 알림 전송

연속 수치는 MVP 에이전트 계약에 전달하거나 후보 점수화에 연결하지 않는다. 연결하려면 계약 변경과 개발 리드 승인이 선행되어야 한다.

## 한계·주의사항

- 합성 데이터의 생성 규칙·라벨 비율·피처 중요도는 실사용자로 일반화할 수 없다.
- 타깃이 이진이라 제품의 `PARTIAL`을 표현하지 못한다.
- 웨어러블 유무 세그먼트는 만들 수 없다.
- 시간 test의 모든 행이 이력 29일 이상이어서 콜드스타트를 충분히 평가하지 못한다.
- 경험 구간별 편차가 크다. 자체 데이터와 공정성 검증 없이 하나의 임계값을 적용하지 않는다.
- 이 아티팩트는 scikit-learn 1.9.0 직렬화 환경에서 생성되었다. 라이브러리 버전이 다른 환경에서는 재검증이 필요하다.

## 입력·출력

- 입력: 아래 19개 피처를 가진 표형의 DataFrame
- 출력: `predict_proba` 양성 클래스 1의 오프라인 합성 데이터 기준 수행 성향 점수. 공개 API 응답이 아님

## 재현 정보

| 항목 | 값 |
|---|---|
| seed | 42 |
| git commit | `84e53a05f01e9188b5d2ed16fdfc6d99da3afcf0` |
| joblib | 1.5.3 |
| matplotlib | 3.10.5 |
| numpy | 2.5.2 |
| pandas | 2.3.3 |
| pyarrow | 21.0.0 |
| PyYAML | 6.0.3 |
| scikit-learn | 1.9.0 |
| 모델 SHA-256 | `3970a2b63519ab70045953046965fbc15970fa2380160be379f874e06ff074cf` |
| freeze SHA-256 | `51128a1bb87fe1ff0c5057a855afad6a02419522e5cb4fe2261377bf05b34a7c` |
| 재로드 예측 | 저장 `float32` 예측값 5,382건 일치, 최대 차이 0 |

## 아티팩트·근거 자료

- [final_model_A3_histgb.joblib](final_model_A3_histgb.joblib)
- [final_model.yaml](../config/final_model.yaml)
- [final_metrics.json](../outputs/final/final_metrics.json)
- [ML_학습결과서.md](../reports/ML_학습결과서.md)
- [FINAL_VERIFICATION.md](../reports/FINAL_VERIFICATION.md)

## 출처

- [ML_WORK_PLAN.md](../docs/ML_WORK_PLAN.md)
- [FEATURE_SPEC.md](../docs/FEATURE_SPEC.md)
- [experiments.yaml](../config/experiments.yaml)
- [final_model.yaml](../config/final_model.yaml)
- [Whoop Fitness Dataset](https://www.kaggle.com/datasets/likithagedipudi/whoop-fitness-dataset)
