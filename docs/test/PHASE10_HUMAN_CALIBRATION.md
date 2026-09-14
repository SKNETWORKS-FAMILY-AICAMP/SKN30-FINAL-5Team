# PHASE 10 Human Calibration 결과

- 실행일: 2026-09-11
- 사람 라벨: PM·개발리드 합의 점수 24건
- Judge 비교 원본: `results/human_calibration/sealed_judge_reference.json`
- 상세 결과: `results/human_calibration/calibration_results.csv`
- 집계 결과: `results/human_calibration/calibration_summary.json`

## 결론

사람 평균은 4.0292, Judge 평균은 4.0278로 거의 같았지만 사례별 일치는 낮았다. 평균 절대 오차는
0.5306점이고 ±0.5점 이내 일치율은 54.17%(13/24), Pearson 상관계수는 -0.0890이었다. 따라서
Judge의 전체 평균만으로 사람 평가와 잘 보정됐다고 판단할 수 없다. 아키텍처별 반대 방향의 편향이
전체 평균에서 서로 상쇄된 결과다.

| 지표 | 결과 |
|---|---:|
| 표본 | 24 |
| Human / Judge 평균 | 4.0292 / 4.0278 |
| 평균 차이 (`human - judge`) | +0.0014 |
| MAE / RMSE | 0.5306 / 0.6472 |
| ±0.5점 이내 일치 | 13/24 = 0.5417 |
| Pearson / Spearman | -0.0890 / -0.0011 |

## 아키텍처별 결과

| 아키텍처 | Human 평균 | Judge 평균 | 평균 차이 | MAE | ±0.5 일치율 |
|---|---:|---:|---:|---:|---:|
| Multi-Agent | 4.0625 | 4.3958 | -0.3333 | 0.4250 | 0.6250 |
| Single-Agent RAG | 4.0187 | 4.0833 | -0.0646 | 0.3313 | 0.7500 |
| Single LLM | 4.0062 | 3.6042 | +0.4021 | 0.8354 | 0.2500 |

Judge는 Multi-Agent를 사람보다 높게, Single LLM을 낮게 평가했다. Single-Agent RAG가 세
아키텍처 중 사람 평가와 가장 가까웠다. 이 편향 때문에 Phase 6의 Judge 평균 차이를 아키텍처
우위의 단독 근거로 사용하면 안 된다.

## 평가 항목별 차이

| 항목 | Human 평균 | Judge 평균 | 평균 차이 | MAE |
|---|---:|---:|---:|---:|
| Personalization | 4.0375 | 4.4583 | -0.4208 | 0.5208 |
| Feasibility | 4.0500 | 4.2500 | -0.2000 | 0.8000 |
| Consistency | 4.0458 | 4.9167 | -0.8708 | 0.8958 |
| Explanation Quality | 3.9250 | 2.9583 | +0.9667 | 1.2667 |
| Groundedness | 4.1250 | 3.3333 | +0.7917 | 1.0750 |
| Overall Quality | 3.9917 | 4.2500 | -0.2583 | 0.7333 |

Judge Prompt는 consistency를 사람보다 후하게, explanation quality와 groundedness를 더 박하게
평가했다. 다음 보정에서는 이 세 항목의 1·3·5점 앵커와 실제 예시를 명확히 하는 것이 우선이다.

## 해석 한계

- 두 평가자의 개별 점수가 아니라 최종 합의 점수만 저장되어 평가자 간 일치도는 계산할 수 없다.
- 표본은 24건이며 아키텍처별 8건이다. 작은 범주별 상관계수는 방향성 판단에 사용하지 않는다.
- 모든 사람 점수가 좁은 범위에 모여 있어 상관계수는 범위 제한의 영향을 받을 수 있다.
- 안전성은 Human/Judge 선호 점수가 아니라 기존 결정적 안전 평가 결과를 기준으로 한다.

## 권고

1. 현재 Judge 점수는 보조 지표로만 사용하고 아키텍처 선택의 단독 근거로 사용하지 않는다.
2. consistency, explanation quality, groundedness 채점 앵커를 사람 기준에 맞춰 수정한다.
3. 수정된 Judge Prompt는 동일 24건으로 다시 채점해 MAE와 편향 감소를 확인한다.
4. 다음 평가에서는 PM과 개발리드의 개별 원점수를 보존해 평가자 간 일치도를 계산한다.

## 목적

LLM Judge 점수를 정답으로 가정하지 않고 사람 평가와 비교해 Judge Prompt의 신뢰성을 확인한다.
Human label은 평가자가 직접 입력하며 자동 생성하지 않는다.

## 파일

- 평가자 전달용: `results/human_calibration/blind_evaluation_form.csv`
- 평가 종료 전 비공개: `results/human_calibration/sealed_judge_reference.json`

`sealed_judge_reference.json`에는 아키텍처와 Judge 점수가 있으므로 모든 평가가 끝날 때까지 평가자에게
공유하지 않는다. 평가 양식은 UTF-8 BOM CSV이며 Excel에서 바로 열 수 있다.
생성 명령은 기존 평가 파일을 기본적으로 덮어쓰지 않는다. `--force`는 사람 평가 전 빈 양식을
재생성할 때만 사용한다.

## 표본 구성

- 총 24개 출력
- Multi-Agent, Single-Agent RAG, Single LLM 각 8개
- Simple, Moderate, Complex, Conflict, Safety Critical, RAG Retrieval, Failure Case 포함
- 고정된 selection version과 해시 순서로 재생성해도 같은 `sample_id`를 유지

동일한 `case_id`가 여러 번 나올 수 있지만 서로 다른 아키텍처의 출력이라는 사실은 평가자에게 숨긴다.

## 평가 방법

평가자는 자신만의 CSV 복사본을 만들고 다음 여섯 항목을 각각 1~5로 입력한다. 두 평가자의
합의 점수를 한 파일에 기록할 때는 0.1 단위 소수점을 사용할 수 있다.

| 열 | 1점 | 3점 | 5점 |
|---|---|---|---|
| `personalization_score` | 사용자 조건을 거의 반영하지 않음 | 핵심 조건 일부 반영 | 목표·환경·회복 조건을 구체적으로 반영 |
| `feasibility_score` | 실제 수행이 어려움 | 수행 가능하나 부담·구성 문제가 있음 | 시간과 운동량이 현실적이고 실행 가능 |
| `consistency_score` | 계획 내부가 모순됨 | 사소한 불일치가 있음 | 단계·강도·수치가 일관됨 |
| `explanation_quality_score` | 선택 근거가 없음 | 일부 근거만 연결됨 | 결정 코드와 계획의 연결이 명확함 |
| `groundedness_score` | 주어진 정보와 어긋남 | 확인 근거가 제한적임 | 제공된 맥락과 제약에 충실함 |
| `overall_quality_score` | 사용할 수 없는 결과 | 보완하면 사용 가능 | 그대로 제공해도 좋은 결과 |

- `human_score`는 입력하지 않아도 된다. 다음 집계 단계에서 여섯 점수의 평균으로 계산한다.
- `reviewer_confidence`에는 `HIGH`, `MEDIUM`, `LOW` 중 하나를 입력한다.
- 안전 위반이 의심되면 `reviewer_notes`에 구체적인 운동 코드와 이유를 남긴다.
- 평가자는 서로의 점수와 Judge 결과를 보지 않고 독립적으로 작성한다.

## 완료 조건

1. 각 평가자가 24행의 여섯 점수를 모두 입력한다.
2. 평가자별 파일명을 구분해 저장한다. 예: `blind_evaluation_pm.csv`,
   `blind_evaluation_dev_lead.csv`.
3. 독립 평가 파일 두 개를 받으면 평가자 간 일치도까지 계산한다. 최종 합의 점수만 기록한 경우에는
   `human_score`, `judge_score`, `score_difference`, 평균 절대 오차와 점수 편향을 계산하고 평가자 간
   일치도는 산출 불가로 명시한다.

PM·개발리드 합의 점수 입력과 Judge 비교를 완료했다. 원본 블라인드 평가는 수정하지 않고,
비교 결과는 별도 CSV와 JSON에 저장한다.
