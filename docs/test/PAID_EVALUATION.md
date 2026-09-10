# PAID_EVALUATION.md

유료(LLM 실호출) 평가 실행 절차와 예산 산정. PHASE 3(실 임베딩), 4, 5가 대상이다.

**원칙**: `--confirm-spend` 없이는 어떤 provider 호출도 발생하지 않는다.
기본 동작은 dry-run이다.

---

## 1. 예상 호출량 (실측, 가격 무관)

`uv run python -m backend.tests.evaluation.budget_cli`로 언제든 재계산할 수 있다.
호출 수는 그래프 구조에서, 토큰량은 **실제 어댑터가 만드는 prompt를 직렬화해서**
측정한 값이다. repair 1회분 여유(×1.25)를 이미 포함한 상한이다.

| Phase | 대상 | LLM 호출 | prompt tokens | output(상한) | output(실측 기반) |
|---|---|---|---|---|---|
| 4 pilot | 14 case × 1회 | 56 | 259,358 | 280,000 | 116,375 |
| 4 variance | 14 case × 3회 | 168 | 778,074 | 840,000 | 349,125 |
| 5 judge | 14 plan × 1회 | 14 | 24,331 | 10,500 | 8,750 |
| **합계** | | **238** | **1,327,202** | **1,130,500** | **470,750** |

output 두 열의 차이가 크다. 상한은 `LLM_AGENTS_MAX_OUTPUT_TOKENS=4000`을 모든
호출이 소진한다고 가정한 값이고, 실측 기반은 역할별 실제 출력량을 쓴 값이다.

| 역할 | 실측 output tokens | 출처 |
|---|---|---|
| TRAINING | ~2,900 | `config.py` 주석 (2,375–2,893) |
| COORDINATOR | ~2,900 | `config.py` 주석 (2,047–2,913) |
| RECOVERY | ~400 | 본 harness 첫 실호출 (358) |
| FEASIBILITY | ~400 | 본 harness 첫 실호출 (324) |
| JUDGE | ~500 | 스키마상 6개 점수 + 짧은 근거 |

**예산 판단은 실측 기반 열을 쓰는 것이 맞다.** 상한만 보면 약 2.4배 과대 추정된다.

역할별 1회 실행 prompt (평균):

| 역할 | ~tokens |
|---|---|
| TRAINING | 4,666 |
| RECOVERY | 4,278 |
| FEASIBILITY | 4,279 |
| COORDINATOR | 5,300 |
| **1회 실행 합계** | **~18,523** |

prompt가 큰 이유는 세 Agent와 Coordinator가 **각각 승인된 운동 pool 전체를**
입력으로 받기 때문이다(`payload.py`의 `_POOL_EXERCISE_FIELDS`). 이는 설계상
의도된 것이며 Agent가 pool 밖 운동을 만들지 못하게 하는 근거이기도 하다.

### 1.1 축소 옵션

variance 3회 반복이 전체 비용의 약 59%를 차지한다. 예산이 빠듯하면:

```bash
# variance 생략: 70 호출, prompt ~284K / output ~125K (전체의 약 21%)
uv run python -m backend.tests.evaluation.paid_run_cli --confirm-spend --repeats 1
```

다만 `temperature=0`이 결정론을 보장하지 않으므로, variance를 생략하면
"동일 입력 재현성" 항목은 미측정으로 보고해야 한다.

## 2. 비용 계산

**이 저장소는 벤더 가격을 하드코딩하지 않는다.**
`docs/runbooks/v3-shadow-evaluation.md`:

> Current vendor prices are not hard-coded. ... Do not estimate or write a cost
> when that reference is absent.

따라서 승인된 가격 참조를 넘겨야 금액이 계산된다.

```bash
uv run python -m backend.tests.evaluation.budget_cli \
  --pricing-reference path/to/pricing.json
```

`pricing.json`은 `V3ApprovedPricingReference` 스키마를 따른다:

```json
{
  "pricing_schema_version": "v3-approved-pricing-v1",
  "provider_code": "OPENAI",
  "model_code": "gpt-5.6-terra",
  "currency_code": "USD",
  "input_token_unit": 1000000,
  "output_token_unit": 1000000,
  "input_unit_price": "0.00",
  "output_unit_price": "0.00",
  "effective_at": "2026-09-10T00:00:00+00:00",
  "source_reference": "<가격표 출처>"
}
```

수기 계산이 필요하면:

```
실측 기반 = 1.327 × (input 단가/1M) + 0.471 × (output 단가/1M)
상한      = 1.327 × (input 단가/1M) + 1.131 × (output 단가/1M)
```

## 3. 실행 절차

### 3.1 OpenAI 키

Secrets Manager `/helkki/staging/openai-api-key`에 있다. **평문 문자열**이며
JSON 객체가 아니므로 그대로 쓰면 된다(확인함).

```bash
export PYTHONIOENCODING=utf-8 PYTHONUTF8=1
# Git Bash는 '/helkki/...'를 Windows 경로로 변환해버린다. 이 변수가 없으면
# aws가 "Invalid name" 오류를 낸다.
export MSYS_NO_PATHCONV=1
export OPENAI_API_KEY=$(aws secretsmanager get-secret-value \
  --region ap-northeast-2 \
  --secret-id '/helkki/staging/openai-api-key' \
  --query SecretString --output text)
```

AWS 세션이 만료되면 `aws login`으로 재인증해야 한다. 키 값을 파일·픽스처·
결과물·로그에 기록하지 않는다.

### 3.2 LangSmith 키 (선택)

Secrets Manager에 **없다.** 필요하면 별도 발급 후:

```bash
export LANGSMITH_API_KEY=...
export LANGSMITH_PROJECT=helkki-service-quality
```

없어도 평가는 정상 수행된다. 상세는 `docs/test/LANGSMITH_TRACING.md`.

### 3.3 실행

```bash
# 1) dry-run으로 호출량 확인 (비용 0)
uv run python -m backend.tests.evaluation.paid_run_cli --dry-run

# 2) 소규모 파일럿부터 (호출 상한을 낮게)
uv run python -m backend.tests.evaluation.paid_run_cli --confirm-spend --max-calls 20

# 3) 결과 검토 후 전체
uv run python -m backend.tests.evaluation.paid_run_cli --confirm-spend --max-calls 300 --repeats 3
```

`--max-calls`는 각 실행 직전에 확인하는 **하드 스톱**이다. 설정 오류로 전체
dataset이 소진되는 사고를 막는다.

### 3.4 실 임베딩 검색 평가

```bash
uv run python -m backend.tests.evaluation.report_retrieval_cli --real-embeddings
```

임베딩은 매우 저렴하다(18 document + 8 query = 26회 호출, 수천 토큰 수준).

## 4. 산출물

```
results/
├── retrieval_metrics.json      # PHASE 3
├── retrieval_cases.csv
└── paid/
    ├── agent_metrics.json      # PHASE 4 (7개 지표)
    ├── evaluation_summary.json # 결정적 판정 결과
    ├── latency_metrics.json    # P50/P95 (실 provider 기준)
    └── judge_scores.json       # PHASE 5
```

## 4.1 배포 설정 정합성 (중요)

평가 runner는 `infra/deployment/compose.staging.v3production.yaml`을 그대로
반영한다.

| 항목 | 배포값 | 라이브러리 기본값 |
|---|---|---|
| `V3_EXECUTION_PROFILE` | `PRODUCTION` | `DEMO` 아님 |
| `LLM_AGENTS_TIMEOUT_SECONDS` | **60** | 5.0 |
| `LLM_AGENTS_MAX_OUTPUT_TOKENS` | **4000** | 1200 |
| `LLM_AGENTS_MODEL_CODE` | `gpt-5.6-terra` | `unconfigured` |

기본값으로 실행하면 **Training이 5초 deadline에서 취소되고 결정적 fallback이
대신 계획을 만든다.** 상태는 `SUCCEEDED`로 보이지만 LLM은 계획을 만들지 않은
것이므로 멀티에이전트를 측정한 결과가 아니다. `config.py`가 이미
"a reasoning model needs both raised or every specialist call fails"라고
경고하고 있다. 실측 latency는 Recovery 4.2초, Feasibility 4.0초로 5초에
근접하며 Training은 초과한다.

## 5. 안전장치 요약

| 장치 | 위치 |
|---|---|
| `--confirm-spend` 없으면 호출 0 | `paid_run_cli.py` |
| `--max-calls` 하드 스톱 | `paid_run_cli.py` |
| provider 게이트(승인 모델만) | `openai.py::openai_demo_gates_ready` |
| Safety BLOCKED case는 호출 0 | `nodes.validate_entry` |
| 결정적 실패 시 judge 호출 안 함 | `judge.py::judge_run` |
| 가격 참조 없으면 금액 미기재 | `budget.py` |

## 6. 주의

- **Judge 모델이 Agent 모델과 같으면 self-preference 편향이 있다.**
  `EVAL_JUDGE_MODEL_CODE`로 분리할 수 있으며, 결과에는 항상 `model_label`이
  기록된다. 보고서에 이 한계를 명시할 것.
- PHASE 6(Single vs Multi)은 별도 작업이며 이 문서 범위가 아니다.
  동일 조건 보장 체크리스트는 `docs/test/TEST_PLAN.md` PHASE 6을 따른다.
