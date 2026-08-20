# ML_WORK_PLAN.md

운동 수행 여부 예측 ML 과제의 **실행 계획**과 3인 분배 문서다.

| 항목 | 값 |
|---|---|
| 인원 | 3명 |
| 작업 방식 | **3인 각자 코딩 에이전트 사용** (11절 규칙 필수) |
| 작업 위치 | 저장소 루트 `ml/` |
| 산출물 | **① 머신러닝 학습 결과서 ② 학습한 ML 모델** |

---

## 0. 문서 위치와 적용 순서

제품 규칙과 충돌하면 다음 순서를 따른다.

1. `docs/DOMAIN_RULES.md` (제품 불변조건)
2. `AGENTS.md`, `data/AGENTS.md` (작업 규칙)
3. 이 문서

**확정 사항**

- ML은 런타임 결정에 연결하지 않는다. 오프라인 분석 전용이다.
- 딥러닝을 사용하지 않는다.
- 합성 데이터만 사용한다. 실사용자 데이터는 투입하지 않는다.

**선행 확인 필요 (작업 시작과 병행)**

- 루트 `ml/` 디렉터리는 `AGENTS.md` 3절 소유권 표에 없는 신규 영역이다.
  아키텍처 변경에 해당하므로 **개발 리드 확인**을 받는다. 확인 전에도 작업은 진행하되,
  PR 본문에 신규 디렉터리 추가 사실과 사유를 명시한다.

---

## 1. 과제 정의

### 1.1 목표

> 합성 웨어러블·운동 이력 데이터로 전일까지의 정보를 사용해 당일 운동 수행 여부를 예측하고,
> **어떤 정보 블록이 예측에 기여하는지, 어떤 사용자 구간에서 작동하는지**를 확인한다.

정확도 수치 자체가 목표가 아니다.

### 1.2 타깃 정의와 한계

```text
workout_completed = 0  해당 날짜에 운동 기록 없음
workout_completed = 1  해당 날짜에 운동 기록 있음
```

**이 타깃은 제품의 공식 수행 상태가 아니다.**

`docs/DOMAIN_RULES.md` 476행의 공식 상태는 `COMPLETED` / `PARTIAL` / `NOT_COMPLETED` 3값이며,
463행에 따라 앱 내 운동 블록 체크로만 확정된다.

이 모델이 예측하는 것은 **활동 발생 여부**이지 **계획 준수 여부**가 아니다.
이진화 과정에서 `PARTIAL` 구간은 표현되지 않는다. **결과서에 이 한계를 반드시 적는다.**

### 1.3 표현 규칙 (결과서 작성 시 강제)

| 금지 표현 | 허용 표현 |
|---|---|
| 실제 운동 성공확률 | 합성 데이터 기준 수행 성향 점수 |
| 계획한 운동의 성공 여부 | 해당 날짜의 운동 기록 존재 여부 |
| 루틴 조정으로 성공률이 향상된다 | (주장하지 않음) |
| 웨어러블은 예측에 도움이 안 된다 | 이 합성 데이터셋에서는 추가 기여가 관측되지 않았다 |
| 최근 수행률이 높으면 실제 성공률이 상승한다 | 합성 데이터에서 최근 수행률이 주요 예측 특성으로 나타났다 |

**피처 중요도는 합성 생성기의 특성일 수 있다. 실사용자 행동 가설로 승격하지 않는다.**

### 1.4 ML이 하지 않는 것

`docs/DOMAIN_RULES.md`에 따라 다음을 절대 수행하지 않는다. **모델 카드에도 명시한다.**

- 통증·이상 반응 판단
- 안전 veto 생성 또는 변경
- `REST` / `STOP_AND_SEEK_HELP` 결정
- 운동 강도·난이도 결정
- 사용자 요청 시간 단축 (39행)
- 웨어러블만으로 계획 변경 (32행)
- 운동 완료 상태 자동 판정 (463행)
- 미수행 가능성을 근거로 한 압박 알림 (43행)

현행 계약 참고: 421행은 **opaque confidence 점수를 MVP 에이전트 계약에서 배제**하고,
441행은 후보 점수화를 **결정적 Python 규칙**의 영역으로 지정한다.
따라서 연속 점수를 에이전트에 넣으려면 계약 변경과 개발 리드 승인이 선행된다. **이번 범위 밖이다.**

---

## 2. 산출물 명세

### 산출물 ① 머신러닝 학습 결과서

경로: `ml/reports/ML_학습결과서.md`

**목차를 아래로 고정한다.** Track C가 작업 시작 시점부터 이 뼈대에 채워 넣는다.

```text
1. 과제 정의        목표, 타깃 정의, 타깃 한계(PARTIAL 소실)
2. 데이터           출처, 라이선스, 규모, 합성 데이터 명시
3. 라벨 구조        분포, lag-1 자기상관, 요일 주기성
4. 전처리           파이프라인, 누수 차단 목록과 검증 결과
5. 분할             시간 기반 / 사용자 기반
6. 실험 설계        ablation A0~A5, A2-lag1, 모델 3종
7. 결과             전체 성능표 (두 분할)
8. 세그먼트 분석    이력 길이 / experience_level_code, A2 vs A3 비교
9. Calibration      Brier, calibration curve
10. 해석            계수, permutation importance
11. 한계            합성 데이터 한계, 콜드스타트, 인과 불가
12. 결론과 향후 과제
```

### 산출물 ② 학습한 ML 모델

경로: `ml/models/`

- `model_<ablation>_<model>.joblib` — **전처리를 포함한 sklearn Pipeline 객체**로 저장한다.
  전처리를 분리해서 저장하면 재현이 깨진다.
- `MODEL_CARD.md` — 아래 항목 필수

```text
학습 데이터        출처, 합성 여부, 규모, 기간
입력 피처          컬럼 목록과 정의
타깃               정의와 한계
분할               방식
성능               validation / test 주요 지표
선정 근거          왜 이 모델인가
사용 금지 범위     1.4절 전체
재현 정보          seed, git_commit, 라이브러리 버전
```

**모델 선정 규칙: validation PR-AUC 최고 모델 1개.** test 성능을 보고 선정하지 않는다.

---

## 3. 작업 분배

| 트랙 | 담당 | 책임 |
|---|---|---|
| **A** 데이터 | **장규원** | 데이터셋 정확성, **누수 차단** |
| **B** 모델링·실험·평가 | **박세빈** | 실험 매트릭스, 지표 산출, 모델 아티팩트 |
| **C** 최종 점검·산출물 | **채동현** | **독립 검증**, 결과서·모델 카드 집필 |

> A는 임계 경로다. A가 늦으면 전원이 멈춘다. **가장 여유 있는 사람이 A를 맡아야 한다.**
>
> **B가 모델과 그 평가를 함께 만들므로, 수치를 검증할 독립적인 눈이 없다.**
> 그래서 C의 첫 번째 책임은 집필이 아니라 **독립 검증**이다. C는 B의 코드를 쓰지 않고
> 최소 1개 지표를 직접 재계산해 대조한다. 이것이 C를 별도 트랙으로 두는 이유다.

---

### Track A — 데이터

**임계 경로.** 인계 1이 늦으면 B와 C가 함께 멈춘다.

1. **원본 확보 및 메타데이터 기록** — 출처 URL, CC0, 취득일, **합성 데이터 명시**
2. **라벨 구조 확인** (전처리보다 먼저)
   - `workout_completed` 분포, **lag-1 자기상관**, 요일별 수행률, 사용자별 이력 길이 분포
   - → 결과서 3절 원고를 바로 작성해 C에게 전달
3. **전처리 구현**

   ```text
   user_id + local_date 정렬
   → 당일 결과성 컬럼 제외
   → 전일 컨디션 값 shift(1)
   → 최근 7일·28일 이력 피처
   → 개인 기준선 delta
   → 결측 처리 + 가용성 플래그
   ```

4. **누수 차단 검증 (자동화, fail closed)**
   - 아래가 최종 데이터셋에 **없음**을 스크립트로 단언한다
   - 당일 `activity_type`, `activity_duration_min`, `activity_strain`, `activity_calories`,
     `avg_heart_rate`, `max_heart_rate`, `hr_zone_1_min`~`hr_zone_5_min`, `workout_time_of_day`
   - **당일 `day_strain`, `calories_burned`** (운동 포함 계산)
   - **`hrv_baseline`, `rhr_baseline`** (사용자당 전기간 상수 -> 미래 정보 + 사용자 지문)
   - 실패 시 파이프라인 중단
5. **결측 처리** — 0으로 대체하지 않는다. 사용자별 중앙값 또는 최근 관측값.
   **단, 이 데이터셋에는 웨어러블 결측이 없다.** 가용성 플래그를 만들지 않는다 (분산 0)
6. **분할 두 벌** — 시간 기반(70/15/15), 사용자 기반(70/15/15).
   롤링 피처는 **분할 전에 사용자별 시간순으로** 계산한다

**전달물**: 분할 데이터셋 6개 파일, `FEATURE_SPEC.md`, 결과서 3·4·5절 원고

---

### Track B — 모델링·실험·평가

1. **실험 프레임** — 설정 기반 실행, 시드 고정, 결과 자동 기록
2. **Ablation** (피처 블록은 A의 `FEATURE_SPEC.md` `block` 태그를 따른다)

   **확정된 정의는 `ml/config/experiments.yaml`과 `ml/docs/FEATURE_SPEC.md` 7절에 있다.**

   | ID | 포함 | 전이 가능성 |
   |---|---|---|
   | `A0` | 다수 클래스 | — |
   | `A1` | 프로필·달력 | 높음 (콜드스타트 상한) |
   | `A2` | + 운동 이력 | **최상** (앱이 직접 기록) |
   | `A3` | + 웨어러블 (서비스 수집 가능) | 높음 |
   | `A4` | + 개인 기준선 | 높음 |
   | `A5` | + HRV·recovery | **없음** (서비스 미수집, 탐색 전용) |
   | `A2-lag1` | 자기상관 참조선 | — |

   **핵심 비교는 `A2` → `A3`이다.** 웨어러블이 앱 기록 대비 추가 정보를 주는지가
   서비스 설계에 직결된다.

   `A2-lag1`도 중요하다. 전체 모델이 이 수준을 넘지 못하면 나머지 피처는 기여가 없다는 뜻이고,
   그 자체가 유효한 결과다.

3. **모델** — Logistic Regression, Random Forest, HistGradientBoosting
4. **매트릭스** — 2개 분할 × 6개 ablation × 3개 모델 (`A0`는 분할당 1회)
5. **하이퍼파라미터** — **기본값 우선.** 여유가 있을 때만 소폭 탐색.
   validation으로만 조정하고 **test는 최종 1회**만 사용한다
6. **지표 산출** — Precision, Recall, F1, ROC-AUC, PR-AUC, **Brier**,
   calibration curve, confusion matrix. 정확도만 내지 않는다
7. **세그먼트별 지표** — 이 과제의 핵심 산출물

   | 세그먼트 | 구간 | 답하는 질문 |
   |---|---|---|
   | `history_bucket` | `0-7` / `8-28` / `29+` | **콜드스타트 사용자에게 무엇이 가능한가** |
   | `experience_level_code` | 수준별 | 특정 집단에서만 작동하는가 |

   **이력 길이가 가장 중요하다.** 서비스 타깃이 운동 초보자·복귀 사용자이고
   `docs/DOMAIN_RULES.md` 354행이 콜드스타트 사용자를 별도로 다룬다.
   `A1` 성능이 곧 콜드스타트 구간의 실질 상한이므로 별도 보고한다.

   웨어러블 유무 세그먼트는 없다. 원본에 결측이 없어 불가능하며 `A2` vs `A3`가 대신 답한다.
8. **해석** — LR 계수, permutation importance.
   **`FEATURE_SPEC.md` 1.1절의 lag-1 상관(0.155)과 대조**해 관측된 중요도가
   자기상관으로 설명되는지 판단한다
9. **모델 아티팩트** — 2절 산출물 ② 규격대로 Pipeline 통째 저장.
   **저장 모델을 재로드해 예측이 일치하는 출력을 남긴다**

**전달물**: `experiments.csv`, **`predictions/*.parquet`**, 결과 표·그림,
`model_*.joblib`, 모델 카드용 성능 수치

> 결과 표를 만들었더라도 `predictions/*.parquet`를 반드시 함께 넘긴다.
> C가 독립적으로 재계산할 유일한 수단이다.

---

### Track C — 최종 점검·산출물

**두 산출물의 최종 책임자다. 인계를 기다리지 않고 처음부터 결과서를 쓴다.**

#### 대기 없이 시작하는 집필

결과서 12개 절 중 **7개는 확정된 스펙과 실측값만으로 지금 쓸 수 있다.**

| 절 | 근거 |
|---|---|
| 1. 과제 정의 | 이 문서 1절 |
| 2. 데이터 | `FEATURE_SPEC.md` 1절 실측 |
| 3. 라벨 구조 | `FEATURE_SPEC.md` 1.1절 실측 (기저율 0.5401, lag-1 0.155, 평일 0.59 / 주말 0.418) |
| 4. 전처리 | `FEATURE_SPEC.md` 3·4절 (검증 *결과*만 인계 1 이후) |
| 5. 분할 | `experiments.yaml` splits |
| 6. 실험 설계 | `FEATURE_SPEC.md` 7절 ablation 표 |
| 11. 한계 | 합성 데이터, `PARTIAL` 소실, 콜드스타트, 웨어러블 결측 없음 |

#### 독립 검증 (C의 첫 번째 책임)

B가 모델과 그 평가를 함께 만들므로 **수치를 확인할 독립적인 눈이 C뿐이다.**

1. **지표 재계산** — B의 `metrics.py`를 쓰지 말고 `predictions/*.parquet`에서
   **최소 1개 지표를 직접 계산**해 B의 결과 표와 대조한다. 불일치는 즉시 보고한다
2. **누수 교차 확인** — 최종 데이터셋 컬럼 목록을 `experiments.yaml`의 `excluded`와 대조한다.
   특히 `day_strain`, `calories_burned`, `hrv_baseline`, `rhr_baseline`
3. **재현성 확인** — 저장 모델을 직접 로드해 예측이 재현되는지 실행한다
4. **선정 규칙 확인** — 제출 모델이 **validation** PR-AUC 기준으로 뽑혔는지,
   `A5`가 후보에서 제외됐는지 확인한다

#### 산출물 집필

5. **결과서 7~10·12절** — 인계 2 이후 결과를 채운다
6. **모델 카드** — 2절 규격. **1.4절 사용 금지 범위를 반드시 포함**한다
7. **표현 규칙 검증** — 1.3절 금지 표현과 인과 주장이 없는지 최종 확인한다
8. **제출 체크리스트** — 9절 전 항목 확인

**전달물**: `ml/reports/ML_학습결과서.md`, `ml/models/MODEL_CARD.md`, 검증 결과

---

## 4. 인터페이스 계약

**스키마는 확정되었다.** 아래 두 파일이 단일 기준이며, 세 트랙 모두 이것을 따른다.

| 파일 | 내용 |
|---|---|
| `ml/docs/FEATURE_SPEC.md` | 피처 컬럼 명세, 제외 근거, 예측 결과 스키마 |
| `ml/config/experiments.yaml` | 피처 블록, ablation, 모델, 분할, 평가 설정 |

스키마를 새로 정하지 말고 **아래 2가지만 확인**한 뒤 바로 착수한다.

1. `FEATURE_SPEC.md` 6절 `experience_level_code` 매핑 — 서비스 확정 코드값이 3종과 다르면 갱신
2. 세 명이 파일 소유(8절)와 브랜치를 확인

원본 컬럼은 실제 데이터 파일을 열어 이미 확정했다. 추가 확인이 필요 없다.

### 서비스 정렬에서 확정된 핵심 사항

> **서비스 `wearable_summaries`에는 HRV와 recovery score가 없다** (`docs/DATA_MODEL.md` 7.7절).

따라서 웨어러블 블록을 둘로 분리했다.

- `A3` 서비스 수집 가능: `sleep_minutes`, `resting_hr`(+3값 trend code), `active_minutes`, `steps`, `average_heart_rate`
- `A5` 서비스 미수집: `hrv`, `recovery_score` — **결과가 좋아도 제품 설계 근거로 쓰지 않는다**

또한 `age`·`gender`는 `docs/DOMAIN_RULES.md` 8절(만 나이를 에이전트 입력에 포함하지 않음)에 따라
피처에서 제외했다. 제품에서 쓸 수 없는 피처는 학습에도 넣지 않는다.

---

## 5. 진행 순서와 인계 지점

시간 배분은 팀이 조절한다. 이 절은 **의존 관계만** 규정한다.

```text
[전원] 골격 커밋 -> 각자 트랙 브랜치 분기
   |
   +-- A 데이터 --------------+
   |                          +--> 인계 1: A -> B (데이터셋)
   +-- B 실험 프레임 ---------+                |
   |                                           +--> B 실험 실행 + 지표 산출
   +-- C 결과서 1~6·11절 집필                   |
        (인계를 기다리지 않는다)                +--> 인계 2: B -> C (결과·예측·모델)
                                                        |
                                                        +--> C 독립 검증 -> 통합 -> 제출
```

### 인계 1 — A → B

| 항목 | 내용 |
|---|---|
| 전달물 | 분할 데이터셋 6개 파일 |
| **성립 조건** | `validate_leakage.py` **통과 출력을 붙여넣어야** 인계로 인정한다 |

### 인계 2 — B → C

| 항목 | 내용 |
|---|---|
| 전달물 | `experiments.csv`, `predictions/*.parquet`, 결과 표·그림, `model_*.joblib` |
| **성립 조건** | 저장 모델을 **재로드해 예측이 일치**하는 출력을 붙여넣어야 한다 |

> `predictions/*.parquet`는 결과 표가 있어도 반드시 전달한다.
> C가 B의 코드를 거치지 않고 지표를 재계산할 유일한 수단이다.

### 인계를 기다리지 않는 일

- **C는 처음부터 최종 산출물을 쓴다.** 결과서 1·2·3·4·5·6·11절은 확정된 스펙과
  `FEATURE_SPEC.md` 1절 실측값만으로 작성 가능하다. 더미 데이터가 필요 없다.
- **B는 실험 프레임을 먼저 만든다.** 완성 후 인계 1까지 A의 누수 검증을 교차 확인한다.
  임계 경로에 인력을 붙이는 것이 전체를 앞당긴다.

### 인계가 늦어질 때

- **인계 1 지연**: A는 시간 기반 분할만 먼저 넘긴다. 사용자 기반은 뒤로 미룬다.
- **인계 2 지연**: C는 `A2` × HistGB 하나만 먼저 받아 7~10절 서식과 그림 틀을 완성한다.

---

## 6. 범위 축소 순서

일정이 빠듯하면 **위에서부터 순서대로 버린다.** 아래 3개는 버리지 않는다.

1. SHAP 제외 (permutation importance로 대체) ← 가장 먼저 버린다
2. `A4` (개인 기준선) ablation 제외
3. 하이퍼파라미터 탐색 전면 제외, 기본값 사용
4. Random Forest 제외 (LR + HistGB만)
5. 사용자 기반 분할 제외 (시간 기반만) — **제외 시 결과서 11절에 한계로 명시**

**절대 버리지 않는 것**

- 누수 차단 검증
- 이력 길이 세그먼트 분석
- Brier / calibration (수행 성향 점수를 언급하려면 필수)

---

## 7. `ml/` 디렉터리 구조

```text
ml/
├── AGENTS.md                    ← 에이전트가 자동으로 읽는 ML 영역 규칙
├── README.md                    실행 방법
├── requirements.txt
├── config/
│   └── experiments.yaml
├── data/
│   ├── Whoop Fitness Dataset/   원본 CSV. 21MB, 재현성 위해 커밋함
│   ├── interim/                 ← .gitignore
│   └── processed/               ← .gitignore
├── src/
│   ├── prepare_data.py          Track A
│   ├── features.py              Track A
│   ├── validate_leakage.py      Track A
│   ├── train.py                 Track B
│   ├── metrics.py               Track B
│   └── evaluate.py              Track B
├── notebooks/
│   └── eda.ipynb                탐색용. 최종 산출물 아님
├── models/                      ← 산출물 ②
│   ├── model_<ablation>_<model>.joblib   Track B
│   └── MODEL_CARD.md                     Track C
├── outputs/
│   ├── experiments.csv
│   └── predictions/
├── docs/
│   └── FEATURE_SPEC.md
└── reports/                     ← 산출물 ①
    ├── ML_학습결과서.md
    └── figures/
```

**주의**: `ml/data/`는 이 과제의 Kaggle 합성 데이터다.
저장소 루트의 `data/`(운동 카탈로그·안전 규칙 도메인 데이터)와 **다른 영역**이며 섞지 않는다.

`.gitignore`에 추가할 항목:

```text
ml/data/interim/
ml/data/processed/
ml/outputs/predictions/
*.joblib.tmp
```

**원본 CSV(21MB)는 커밋한다.** 합성 데이터이고 개인정보가 없으며, Kaggle 계정 없이도
전원이 동일한 입력으로 재현할 수 있게 하기 위한 팀 결정이다.
중간 산출물과 예측 파일은 커밋하지 않는다. 산출물 ②인 최종 모델 `.joblib`은 커밋한다.

---

## 8. 공통 규칙

### 재현성

- 모든 스크립트에 시드를 고정한다
- `experiments.csv`에 `git_commit`을 기록한다
- 노트북 결과를 최종 산출물로 삼지 않는다. 스크립트로 재현 가능해야 한다

### 브랜치와 PR

`docs/COLLABORATION_GUIDE.md`를 따르되, **3인이 각자 에이전트를 돌리므로 브랜치를 분리한다.**
한 브랜치를 셋이 공유하면 에이전트들이 서로의 커밋 위에서 계속 충돌한다.

```text
develop
  └─ feat/<issue>-ml            통합 브랜치 (골격 커밋 후 push)
       ├─ feat/<issue>-ml-data   Track A
       ├─ feat/<issue>-ml-train  Track B
       └─ feat/<issue>-ml-report Track C
```

- `main`, `develop`에 직접 커밋하지 않는다
- **통합 브랜치에는 인계 시점에만 병합한다.** 일정이 짧으므로 통합 브랜치 병합은
  GitHub PR 리뷰 없이 직접 병합하되, 병합자가 diff를 눈으로 확인한다
- **`develop`으로 가는 PR은 마지막에 통합 브랜치에서 1건만** 올린다
- 병합 전 반드시 `git pull --rebase`로 통합 브랜치 최신 상태를 받는다

**파일 소유** — 자기 트랙 파일만 수정한다. 남의 파일이 고쳐져야 하면 직접 고치지 말고 요청한다.

| 트랙 | 소유 파일 |
|---|---|
| A | `ml/src/prepare_data.py`, `ml/src/features.py`, `ml/src/validate_leakage.py`, `ml/docs/FEATURE_SPEC.md` |
| B | `ml/src/train.py`, `ml/src/metrics.py`, `ml/src/evaluate.py`, `ml/config/experiments.yaml`, `ml/models/*.joblib` |
| C | `ml/reports/**`, `ml/models/MODEL_CARD.md` |
| 공용 (변경 시 3인 합의) | `ml/AGENTS.md`, `ml/README.md`, `ml/requirements.txt`, `.gitignore` |

### 금지

- 1.3절 금지 표현, 1.4절 ML 금지 목록
- test 세트를 반복 조회하며 튜닝
- 데이터셋 추가 (Whoop 100K 하나만 사용)
- 합성 데이터 결과를 실사용자 인과 주장으로 전환
- 실사용자 데이터 투입

---

## 9. 제출 전 체크리스트

**산출물 ① 결과서**

- [ ] 2절 목차 12개 항목이 모두 채워졌다
- [ ] 타깃 한계(`PARTIAL` 소실)가 명시됐다
- [ ] 합성 데이터임이 명시됐다
- [ ] 두 분할 결과가 모두 보고됐다 (또는 축소 사유가 명시됐다)
- [ ] 이력 길이 세그먼트 표가 있다
- [ ] Brier / calibration이 보고됐다
- [ ] 1.3절 금지 표현이 없다
- [ ] 인과 주장이 없다

**산출물 ② 모델**

- [ ] 전처리 포함 Pipeline으로 저장됐다
- [ ] 저장된 모델을 로드해 예측이 재현된다
- [ ] `MODEL_CARD.md`에 1.4절 사용 금지 범위가 있다
- [ ] seed / git_commit / 라이브러리 버전이 기록됐다
- [ ] validation 기준으로 선정됐다 (test 기준 아님)

**공통**

- [ ] 누수 검증 스크립트 통과
- [ ] `.env`·시크릿·실사용자 데이터가 diff에 없다
- [ ] PR 본문에 신규 `ml/` 디렉터리 추가 사유가 있다

---

## 10. 결과서 문구

**사용 가능**

> 합성 종단 데이터에서 최근 수행률과 운동 공백이 당일 운동 기록 존재 여부를 예측하는 주요 특성으로
> 나타났다. 다만 데이터가 합성이므로 이 특성 중요도는 생성 규칙의 반영일 수 있으며, 실사용자 행동에
> 대한 근거로 사용하지 않는다. 관측된 관계는 향후 자체 데이터로 검증할 가설로 기록한다.

**사용 금지**

> 최근 수행률을 높이면 실제 운동 성공률이 상승한다.
> 웨어러블 데이터는 운동 수행 예측에 도움이 되지 않는다.

### 한 줄 결론

> **운동 지속 지원 서비스가 전체 프로젝트이며, 수행 여부 예측 ML은 지속과 관련된 패턴을 분석하고
> 향후 개인화 기능을 준비하는 오프라인 외부 모듈이다.**

---

## 11. 코딩 에이전트 운용 규칙

3인이 각자 에이전트를 사용하므로 **병목은 코드 작성 속도가 아니라 계약 불일치와 병합 충돌**이다.
아래 규칙이 지켜지지 않으면 게이트에서 통합이 깨진다.

### 11.1 골격 우선 (코드 작성 전 반드시 수행)

에이전트는 명세가 비면 그럴듯한 값을 **지어낸다.** 세 에이전트가 각자 지어내면 컬럼명·파일명·
스키마가 전부 어긋난다. 따라서 코드를 짜기 전에 아래를 통합 브랜치에 **먼저 커밋하고 push한다.**

- `ml/AGENTS.md` — 에이전트가 자동으로 읽는 ML 영역 규칙
- `ml/docs/FEATURE_SPEC.md` — **작성 완료됨.** 실제 데이터로 확정
- `ml/config/experiments.yaml` — **작성 완료됨.** ablation·제외 목록 확정
- `ml/src/*.py` — 함수 시그니처와 입출력 타입만 있는 빈 파일
- `ml/requirements.txt` — 버전 고정
- `.gitignore` 갱신

**이 골격이 세 에이전트의 공통 참조점이 된다.** 짧은 선투자로 통합 실패를 막는다.

### 11.2 에이전트 작업 범위 제한

- **`ml/` 밖을 수정하지 않는다.** `backend/`, `frontend/`, `docs/`(이 파일 제외), `data/`는 건드리지 않는다
- 자기 트랙 소유 파일만 수정한다 (8절 표)
- 저장소 루트 `data/`는 운동 카탈로그 도메인 데이터다. **`ml/data/`와 혼동하지 않는다**
- 의존성을 임의로 추가하지 않는다. 추가 시 `requirements.txt`에 버전을 고정하고 3인에게 알린다
- 포매터를 전체 저장소에 돌리지 않는다. `ml/`에만 적용한다

### 11.3 검증 규칙

`AGENTS.md` 14절: **실행하지 않은 테스트를 통과했다고 말하지 않는다.** 에이전트에도 동일 적용한다.

- 각 트랙은 **실제로 실행한 명령과 출력**을 게이트 시점에 공유한다
- "구현 완료"가 아니라 "이 명령으로 이 출력이 나왔다"로 보고한다
- 특히 Track A의 누수 검증은 **통과 출력을 붙여넣어야** 게이트를 통과한 것으로 본다
- 에이전트가 생성한 수치를 결과서에 옮길 때, 최소 1개는 사람이 직접 재계산해 대조한다

### 11.4 에이전트가 흔히 저지르는 실수 (사전 차단)

| 실수 | 결과 | 차단 방법 |
|---|---|---|
| 결측을 `fillna(0)`으로 처리 | 웨어러블 미착용이 "HRV 0"이 됨 | `ml/AGENTS.md`에 명시 금지 |
| 당일 컬럼을 피처에 포함 | 누수, 성능 비현실적으로 높음 | `validate_leakage.py` fail closed |
| `train_test_split` 무작위 사용 | 같은 사용자가 학습·평가에 동시 존재 | 시간/사용자 분할 명시 |
| 컬럼명 임의 변경 | 트랙 간 통합 실패 | `FEATURE_SPEC.md` 선커밋 |
| `test`로 튜닝 | 성능 과대평가 | validation 전용 규칙 명시 |
| 전처리를 모델과 분리 저장 | 재현 불가 | Pipeline 통째 저장 규칙 |
| 정확도만 보고 | calibration 누락 | 지표 목록 고정 |

### 11.5 트랙별 에이전트 브리프

각자 세션 시작 시 아래를 그대로 전달한다. **공통 도입부**를 먼저 붙인다.

**공통 도입부**

```text
저장소 루트의 AGENTS.md와 ml/AGENTS.md, docs/ML_WORK_PLAN.md를 먼저 읽어라.
작업 범위는 ml/ 디렉터리 안으로 제한한다. ml/ 밖의 파일을 수정하지 마라.
내가 담당한 트랙의 소유 파일만 수정한다.
실행하지 않은 검증을 통과했다고 말하지 마라. 실행한 명령과 실제 출력을 보여라.
컬럼명은 ml/docs/FEATURE_SPEC.md를 단일 기준으로 삼는다. 임의로 만들지 마라.
```

**Track A (채동현)**

```text
담당: ml/src/prepare_data.py, features.py, validate_leakage.py, ml/docs/FEATURE_SPEC.md

입력 파일: "ml/data/Whoop Fitness Dataset/whoop_fitness_dataset_100k.csv"
피처 정의는 ml/docs/FEATURE_SPEC.md 4절에 이미 확정돼 있다. 새로 정하지 마라.

1. 라벨 구조를 먼저 확인해 결과서 3절 원고를 쓴다.
   FEATURE_SPEC 1.1절에 실측값이 있다. 재계산해서 일치하는지 대조하라.
   (기저율 0.5401, lag-1 상관 0.155, 평일 약 0.59 / 주말 약 0.417)
2. 전처리: user_id+local_date 정렬 -> 당일 결과성 컬럼 제외
   -> 전일 값 shift(1) -> 7일/28일 이력 피처 -> 28일 개인 기준선 delta.
   원본 date 컬럼을 local_date로, sleep_hours를 sleep_minutes로(x60) 변환한다.
   day_of_week는 "Monday" 같은 문자열이다. 0=월 ... 6=일 정수로 변환하라.
3. 가용성 플래그를 만들지 마라. 이 데이터셋에는 웨어러블 결측이 없어
   전 행이 True인 분산 0 컬럼이 된다. (유일한 결측은 누수 컬럼 workout_time_of_day)
4. hrv_baseline과 rhr_baseline을 쓰지 마라. 사용자당 전기간 상수이며
   미래 정보와 사용자 지문이 섞여 있다. 개인 기준선은 직전 28일로 직접 계산한다.
5. validate_leakage.py: ml/config/experiments.yaml의 excluded 목록이 최종 데이터셋에
   없음을 단언한다. 하나라도 있으면 예외를 던지고 중단한다. 경고만 하고 넘어가지 마라.
   day_strain과 calories_burned도 당일 값은 누수다.
6. 분할 두 벌: 시간 기반 70/15/15, 사용자 기반 70/15/15.
   롤링 피처는 분할 전에 사용자별 시간순으로 계산한다. 무작위 분할을 쓰지 마라.
   각 분할의 행 수와 사용자 수를 함께 기록한다.
```

**Track B**

```text
담당: ml/src/train.py, metrics.py, evaluate.py, ml/config/experiments.yaml, ml/models/*.joblib

1. FEATURE_SPEC.md의 block 태그로 ablation을 구성한다. 컬럼을 직접 나열하지 마라.
   A0 다수클래스 / A1 기본 / A2 +이력 / A3 +웨어러블 / A4 +개인기준선 / A2-lag1 참조
2. 모델: LogisticRegression, RandomForest, HistGradientBoosting.
   전처리(One-Hot, 표준화)는 sklearn Pipeline 안에 넣는다. 분리하지 마라.
3. 매트릭스: 2개 분할 x 6개 ablation x 3개 모델. A0는 분할당 1회.
4. 하이퍼파라미터는 기본값을 쓴다. 조정이 필요하면 validation으로만 한다.
   test 세트는 최종 1회만 쓴다.
5. 예측 결과를 ML_WORK_PLAN 4.2절 스키마로 저장한다.
   history_days, history_bucket, experience_level_code 컬럼을 반드시 포함한다.
6. 지표를 산출한다. Precision, Recall, F1, ROC-AUC, PR-AUC, Brier,
   calibration curve, confusion matrix. 정확도만 내지 마라.
7. 세그먼트별 지표를 반드시 낸다.
   - history_bucket 0-7 / 8-28 / 29+   <- 가장 중요. 콜드스타트 구간
   - experience_level_code 수준별
   웨어러블 유무 세그먼트는 만들지 마라. 원본에 결측이 없어 불가능하다.
8. 해석: LogisticRegression 계수, permutation importance.
   FEATURE_SPEC 1.1절의 lag-1 상관 0.155와 대조해, 관측된 중요도가
   자기상관으로 설명되는지 판단한다.
9. validation PR-AUC 최고 모델을 Pipeline 통째로 joblib 저장한다. A5는 후보에서 제외한다.
   저장한 모델을 다시 로드해 예측이 같은지 확인하고 그 출력을 보여라.
   모델 카드는 C가 쓴다. 성능 수치와 하이퍼파라미터를 정리해 넘겨라.
```

**Track C**

```text
담당: ml/reports/**, ml/models/MODEL_CARD.md
너는 두 산출물의 최종 책임자다. 인계를 기다리지 말고 지금 집필을 시작한다.

1. ml/reports/ML_학습결과서.md 를 ML_WORK_PLAN 2절의 12개 목차로 만든다.
2. 아래 7개 절을 지금 바로 쓴다. 파이프라인 결과가 필요 없다.
   1·2·3·4·5·6·11절. 근거는 ml/docs/FEATURE_SPEC.md 1절과 1.1절의 실측값,
   그리고 ml/config/experiments.yaml 이다.
   실측: 100,000행 / 286명 / 기저율 0.5401 / lag-1 상관 0.155 /
        평일 약 0.59, 주말 약 0.418 / 웨어러블 결측 없음
3. 인계 2를 받으면 독립 검증을 먼저 한다. 이게 집필보다 우선이다.
   - ml/src/metrics.py 를 쓰지 마라. predictions/*.parquet 에서
     최소 1개 지표를 직접 계산해 B의 결과 표와 대조한다.
   - 최종 데이터셋 컬럼을 experiments.yaml 의 excluded 와 대조한다.
     특히 day_strain, calories_burned, hrv_baseline, rhr_baseline.
   - 저장된 모델을 직접 로드해 예측이 재현되는지 실행한다.
   - 제출 모델이 validation PR-AUC 기준으로 뽑혔는지, A5가 제외됐는지 확인한다.
   불일치를 발견하면 넘어가지 말고 즉시 보고한다.
4. 결과서 7~10·12절을 채운다.
5. MODEL_CARD.md 를 쓴다. ML_WORK_PLAN 1.4절 사용 금지 범위를 반드시 포함한다.
6. 결과서에 인과 주장을 쓰지 마라. ML_WORK_PLAN 1.3절 금지 표현 표를 지킨다.
   "성공률"이라는 단어를 쓰지 말고 "운동 기록 존재 여부"로 쓴다.
7. 타깃 한계(PARTIAL 상태 소실)와 합성 데이터 한계를 11절에 반드시 적는다.
   웨어러블 유무 세그먼트가 불가능하다는 사실과, A2 vs A3 가 대신 답한다는 점도 적는다.
8. 제출 전 ML_WORK_PLAN 9절 체크리스트를 전 항목 확인한다.
```

---

출처: [Whoop Fitness Dataset](https://www.kaggle.com/datasets/likithagedipudi/whoop-fitness-dataset),
`docs/DOMAIN_RULES.md`, `data/AGENTS.md`, `docs/COLLABORATION_GUIDE.md`
