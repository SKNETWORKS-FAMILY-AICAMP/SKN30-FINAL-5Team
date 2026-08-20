# 최종 독립 검증 기록

- 검증일: 2026-08-20
- 범위: Track C 집필 범위
- 원칙: test 재평가 금지 정책을 어기지 않고, 이미 완료된 최종 산출을 재사용했다.

## 결과

| 검증 항목 | 결과 | 근거 |
|---|---|---|
| Validation 선정 규칙 | 통과 | A5 제외 후 38개 전체 중 최고 PR-AUC ID가 `time_A3_histgb`로 동결 후보와 일치 |
| A5 최종 후보 제외 | 통과 | freeze guard와 selection config 모두에 `A5` 제외 명시 |
| Test 접근 제한 | 통과 | `test_evaluation_attempt.json`: `completed`, `max_test_evaluations=1`, 재선정 없음 |
| 누수 차단 | 통과 | 6개 분할에서 22개 제외 컬럼과의 교집합 없음 |
| 모델 형태 | 통과 | `joblib.load` 결과 sklearn `Pipeline`, step은 `preprocessor`, `model` |
| 재로드 예측 | 통과 | 5,382행 동일 데이터 재예측. 저장 Parquet `float32` 예측값과 전 행 일치 |
| 지표 독립 재계산 | 통과 | `ml/src/metrics.py` 미사용, Parquet에서 sklearn 지표를 직접 재계산 |
| 예측 스키마 | 통과 | 11개 컬럼이 `FEATURE_SPEC.md` 계약과 일치 |

## 독립 지표 대조

| 지표 | 직접 재계산 | 보고값 | 절대차 |
|---|---:|---:|---:|
| Precision | 0.6978237602568677 | 0.6978237602568677 | 0 |
| Recall | 0.6703221384509939 | 0.6703221384509939 | 0 |
| F1 | 0.6837965390665968 | 0.6837965390665968 | 0 |
| ROC-AUC | 0.7262033877277623 | 0.7262033877277623 | 0 |
| PR-AUC | 0.7661221980724948 | 0.7661221980724948 | 0 |
| Brier | 0.2090506702661514 | 0.2090506728459463 | 2.58e-9 |

Brier의 차이는 저장 Parquet의 `float32` 확률을 이용해 재계산하면서 생긴 정밀도 오차 범위다. 혼동행렬은 `[[1617, 847], [962, 1956]]`로 일치했다.

## 재로드 대조

- 저장 Parquet와 동일하게 `float32`로 변환한 후 예측값: 최대 차이 0, 일치 `true`
- `float64` 재예측값과 저장 `float32`의 최대 차이: `2.9801584866540054e-08`
- 모델 SHA-256: `3970a2b63519ab70045953046965fbc15970fa2380160be379f874e06ff074cf`
- 예측 Parquet SHA-256: `963c03892353473816f004029c6239681cc43775eb5b04462724015e49d6f4ce`
- freeze manifest SHA-256: `51128a1bb87fe1ff0c5057a855afad6a02419522e5cb4fe2261377bf05b34a7c`

## 선정 증거 대조

- `experiments.csv` 재계산 validation PR-AUC: 0.7643487212645705
- freeze 원본 점수 validation PR-AUC: 0.7643486950569605
- 절대차: `2.62e-8`. 저장 예측값의 `float32` 변환에 따른 정밀도 차이임
- 전체 ID·Ablation·모델·분할은 모두 `time_A3_histgb` / `A3` / `histgb` / `time`으로 일치했다.

## 실행 기록

1. `UV_CACHE_DIR=/private/tmp/skn30-uv-cache uv run --offline python`으로 모델·test CSV·예측 Parquet을 읽고 Pipeline 재로드 예측과 지표를 독립 재계산했다.
2. `ml/src/metrics.py`는 import하지 않았고 `sklearn.metrics`로 예측 Parquet에서 지표를 직접 재계산했다.
3. `validate_leakage.py --input <split> --config ml/config/experiments.yaml`을 6개 분할에 각각 실행했다.

## 출처

- [ML_WORK_PLAN.md](../docs/ML_WORK_PLAN.md)
- [FEATURE_SPEC.md](../docs/FEATURE_SPEC.md)
- [final_model.yaml](../config/final_model.yaml)
- [selection.json](../outputs/selection.json)
- [experiments.csv](../outputs/experiments.csv)
- [final_metrics.json](../outputs/final/final_metrics.json)
- [test_evaluation_attempt.json](../outputs/final/test_evaluation_attempt.json)
