# ML 8단계 인계

## 요약

- 최종 모델: `A3` + HistGradientBoosting sklearn `Pipeline`
- 선정 기준: A5 제외 후 validation PR-AUC 최고 (0.764348695)
- 최종 test: Precision 0.697824, Recall 0.670322, F1 0.683797, ROC-AUC 0.726203, PR-AUC 0.766122, Brier 0.209051
- 재로드 예측: 5,382행 `float32` 예측값 전 행 일치
- 용도: 오프라인 외부 모듈. 제품 런타임·알림·에이전트에 연결하면 안 됨

## 인계 산출

| 구분 | 경로 | 내용 |
|---|---|---|
| 모델 | [final_model_A3_histgb.joblib](../models/final_model_A3_histgb.joblib) | 최종 재학습 sklearn Pipeline |
| 동결 증거 | [final_model.yaml](../config/final_model.yaml) | 선정 증거·피처·하이퍼파라미터·test guard |
| 실험 기록 | [experiments.csv](../outputs/experiments.csv) | 38개 validation 전체 |
| Validation 예측 | [predictions/](../outputs/predictions/) | 전체별 Parquet |
| Test 예측 | [predictions_time_A3_histgb_test.parquet](../outputs/final/predictions_time_A3_histgb_test.parquet) | 최종 5,382행 예측값·세그먼트 |
| 성능표 | [final_metrics.csv](../outputs/final/final_metrics.csv) | 최종 test 지표·confusion matrix 원수치 |
| Calibration | [calibration_curve.csv](../outputs/final/calibration_curve.csv) / [PNG](../outputs/final/calibration_curve.png) | 10-bin 수치·그림 |
| Confusion matrix | [confusion_matrix.png](../outputs/final/confusion_matrix.png) | 임계값 0.5 test 그림 |
| 세그먼트 성능 | [segment_metrics.csv](../outputs/final/segment_metrics.csv) | 이력·경험 구간 |
| 피처 중요도 | [feature_importance.csv](../outputs/final/feature_importance.csv) | permutation PR-AUC importance |
| 결과서 | [ML_학습결과서.md](ML_학습결과서.md) | 12개 필수 목차 |
| 모델 카드 | [MODEL_CARD.md](../models/MODEL_CARD.md) | 용도·금지·재현 정보 |
| 검증 증거 | [FINAL_VERIFICATION.md](FINAL_VERIFICATION.md) | 독립 지표·재로드·누수 검증 |

## 모델 사양

- 피처셋: 19개. 정확한 목록은 [MODEL_CARD.md](../models/MODEL_CARD.md)와 [final_model.yaml](../config/final_model.yaml) 참조
- 모델: `sklearn.ensemble.HistGradientBoostingClassifier`
- 하이퍼파라미터: `learning_rate=0.1`, `max_iter=300`, `random_state=42`
- 전처리: 범주형은 정수 인코딩 + 결측 토큰, 수치형은 학습 세트 중앙값 대체
- 입력: A1 + A2 + A3의 19개 피처. 식별자·세그먼트·타깃·제외 컬럼은 입력하지 않음

## 인수 주의사항

1. `ml/src/final_evaluate.py`를 다시 실행하지 말 것. 이미 test 접근은 소진했고 재실행을 거부한다.
2. 모델 무결성 검증은 SHA-256과 `MODEL_CARD.md`의 라이브러리 버전을 확인한 다음 새 환경에서 다시 검증한다.
3. 제품 적용 전 자체 데이터로 재학습하고 콜드스타트·경험 구간 결과와 calibration을 재검증한다.

## 실행·검증 요약

| 명령 | 결과 |
|---|---|
| 6개 분할 누수 검증 | 6/6 통과 |
| 독립 지표·재로드·문서 정합성 | 통과 |
| `ruff check ml/src ml/tests` | 통과 |
| `pytest -q ml/tests` | 22 통과, 경고 15개 |
| `mypy --explicit-package-bases --ignore-missing-imports ml/src` | 7개 소스 통과 |
| 기본 `mypy ml/src` | 미통과. `metrics` 모듈 중복·pandas/PyYAML/sklearn 스텁 미설치 |
| `ruff format --check ml/src ml/tests` | 미통과. 기존 Track A/B 소유 7개 파일의 포맷 불일치 |

기본 mypy·포맷 검사는 이번 Track C 문서 변경과 무관하며, 소유권이 다른 파일은 직접 수정하지 않았다. 해당 파일 소유자가 포맷과 모듈·스텁 설정을 정리해야 전체 ML 게이트가 통과한다.

## 제출 체크리스트

- [x] 12개 목차 결과서
- [x] 타깃 한계·합성 데이터·인과 해석 금지
- [x] 두 분할 validation 성능·이력 세그먼트·Brier·calibration
- [x] 전처리 포함 Pipeline 저장·재로드 예측 일치
- [x] 누수 검증·A5 제외·validation 선정 근거 확인
- [x] 시드·git commit·라이브러리 버전·모델 해시 기록
- [ ] PR 본문에 신규 `ml/` 디렉터리 사유·테스트 요약·리스크 평가 작성 (아래 문구 사용)

PR 본문 권장 문구:

> `ml/`은 Whoop 합성 데이터로 당일 운동 기록 존재를 분석하는 오프라인 ML 영역입니다. 제품 런타임·알림·데이터베이스와 연결하지 않습니다.

## 출처

- [ML_WORK_PLAN.md](../docs/ML_WORK_PLAN.md)
- [MODEL_CARD.md](../models/MODEL_CARD.md)
- [ML_학습결과서.md](ML_학습결과서.md)
- [FINAL_VERIFICATION.md](FINAL_VERIFICATION.md)
