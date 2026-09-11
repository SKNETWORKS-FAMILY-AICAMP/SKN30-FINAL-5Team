# TEST_PLAN.md

배포 전 서비스 품질 평가 계획. 기준 문서는 `docs/test/service_test_master_prompt.md`,
구현 사실은 `docs/test/TEST_SYSTEM_ANALYSIS.md`다.

- 작업 브랜치: `chore/service-quality-evaluation-harness` (develop에서 분기)
- 분기 기준 커밋: `6deb151`

---

## 0. 실행 원칙 (전 Phase 공통)

1. 기존 서비스 로직을 테스트 통과 목적으로 수정하지 않는다. 수정이 필요하면
   원인과 필요성을 `TEST_RESULTS.md`의 "발견된 결함"에 먼저 기록한다.
2. Target 수치를 결과 확인 후 유리하게 바꾸지 않는다. 목표치는 각 Phase 착수
   전에 이 문서에 고정한다.
3. 서비스 결함과 테스트 코드 결함을 분리해서 기록한다.
4. Secret(API Key, LangSmith Key)은 코드·결과 파일·문서에 남기지 않는다.
5. Runner는 달라도 **Evaluator는 동일**하다. 이것이 Single vs Multi 비교의
   신뢰성 조건이다.
6. 유료 호출이 발생하는 Phase는 착수 전 예상 호출 수와 비용을 산정해 보고하고
   승인을 받는다.

## 0.1 Phase별 실행 가능 여부 (현재 환경 기준)

| Phase | 내용 | 비용 | 상태 (2026-09-11) |
|---|---|---|---|
| 0 | 구조 분석 | 없음 | **완료** |
| 1 | Evaluation Dataset | 없음 | **완료** (smoke 20건 + retrieval 8건) |
| 2 | Deterministic Evaluation | 없음 | **완료** (204 run, critical 0) |
| 3 | Retrieval 평가 | 없음(fake) / 소액(실 임베딩) | **완료** (실 임베딩, R@3 0.59) |
| 4 | Multi-Agent 지표 | 없음(scripted) / 유료(실 LLM) | **완료** (14 case, critical 0) |
| 5 | LLM-as-a-Judge | **유료** | **완료** (12건 채점) |
| 6 | Single vs Multi | **유료** | **완료** (A/B/C × 14 case × 2회) |
| 7 | Pairwise Judge | **유료** | **완료** (3 pair × 14 case × 2 순서) |
| 8 | LangSmith | 없음 | **조사 완료.** 워크플로 trace만 사용 결정 |
| 9 | Performance / Failure | 없음/유료 | 실패 경로 완료, latency 측정 완료 |
| 10 | Human Calibration | 없음 | 양식만 |
| 11 | 결과 산출 | 없음 | 부분 |

---

## PHASE 0. 프로젝트 구조 분석 — 완료

산출물: `docs/test/TEST_SYSTEM_ANALYSIS.md`

핵심 결론 3가지:

- Safety Agent는 존재하지 않으며 존재해서도 안 된다. Safety는 결정적 rule engine
  이고 LLM 상류/하류 양쪽에서 강제된다.
- Qdrant는 자격이 아니라 순위만 담당한다. Recall 지표 해석에 직접 영향.
- LangSmith 비활성은 승인된 privacy 정책이다. 켜는 것이 개선이 아니다.

---

## PHASE 1. Evaluation Dataset 구축

### 목표

동일 입력에서 재실행 가능한 고정 dataset. 모든 case가 `ConstraintEnvelope` +
`ExercisePoolSnapshot`으로 결정론적으로 재구성 가능해야 한다.

### 위치

```
backend/tests/evaluation/datasets/
    smoke_cases.json          # 10~20건, 인프라 검증용
    evaluation_cases.json     # 50~100건으로 확장 (Phase 4 이후)
    retrieval_cases.json      # Phase 3용
```

### Category (마스터 명세 9종 전부)

`simple`, `moderate`, `complex`, `conflict`, `safety_critical`,
`rag_retrieval`, `missing_input`, `invalid_input`, `failure_case`

### Case 스키마

| 필드 | 필수 | 비고 |
|---|---|---|
| `case_id` | O | `SQ-<CATEGORY>-<NNN>` |
| `category` | O | 위 9종 |
| `description` | O | 한국어 서술 |
| `user_input` | O | 정규화 입력(생년월일·나이·식별자 금지) |
| `expected_constraints` | O | envelope로 굳어질 값 |
| `prohibited_actions` | O | 발생하면 즉시 FAIL |
| `expected_agent_behavior` | O | 역할 분리 기대 |
| `expected_safety_result` | O | status/action/veto |
| `expected_relevant_documents` | 선택 | Phase 3 |
| `notes` | 선택 | 판정 근거·한계 |

### 설계 규칙

1. **case_id는 기존 시나리오 코드 체계를 잇는다.** 기존
   `v3_evaluation_fixtures.py`의 `HEALTHY_ORIGINAL`,
   `KNEE_LOAD_EXCLUDED_GOAL_PRESERVED` 등과 매핑 가능하게 둔다.
2. **safety_critical은 단 한 건의 오추천도 식별 가능해야 한다.** 따라서
   `prohibited_actions`에 금지 exercise_id를 명시하고, 평가기는 집계값이 아니라
   case 단위로 위반을 리포트한다.
3. **conflict case는 상충 조건을 최소 2개 이상 동시에 담는다.**
   근력 목표 + 높은 피로 / 수면 부족 + 통증 / 시간 부족 + 장비 제한 /
   선호 운동 + 안전 제외.
4. 개인정보 금지: 생년월일, 만 나이, 이름, 이메일, 원시 웨어러블 샘플,
   GPS, 캘린더 텍스트를 dataset에 넣지 않는다(`AGENTS.md` 8절).

### 재현성 고정

- 시간: `FIXED_TIME = 2026-08-25T09:00:00Z` (기존 fixture와 동일)
- 정책 버전: `policy_version`, `catalog_version`, `safety_rule_version`을
  case에 명시
- exercise_id: dataset에 고정 UUID로 박제

### 완료 기준

- [ ] 9개 category 모두 최소 1건
- [ ] smoke 10~20건
- [ ] 모든 case가 `ConstraintEnvelope.create()` / `ExercisePoolSnapshot.create()`
      통과
- [ ] dataset 로더가 스키마 검증 실패 시 명확히 거부
- [ ] 개인정보 필드 부재를 테스트로 강제

---

## PHASE 2. Deterministic Evaluation

### 목표

LLM Judge 이전에 코드로 판정 가능한 항목을 전부 잡는다. **이 Phase의 결과가
안전성 판정의 1차 근거**이며 Judge 점수가 이를 뒤집지 못한다.

### 위치

```
backend/tests/evaluation/
    __init__.py
    dataset.py                # 로더 + 스키마
    envelope_builder.py       # case → ConstraintEnvelope / Pool
    runners/
        fake_chat.py          # 결정적 scripted BaseChatModel
        run_multi_agent.py    # 현재 멀티에이전트 runner
    evaluators/
        constraint_evaluator.py
        safety_evaluator.py
        structure_evaluator.py
        failure_evaluator.py
    test_dataset_contract.py
    test_deterministic_evaluation.py
    test_graph_termination.py
```

### 검증 항목 (마스터 명세 12항목 매핑)

| # | 명세 항목 | 판정 근거 | 목표 |
|---|---|---|---|
| 1 | Structured Output Schema Validation | Pydantic strict + `*_hash` 자기검증 | 100% |
| 2 | 운동 가능 시간 초과 | `REQUESTED_DURATION_MISMATCH` (±5분) | 위반 0 |
| 3 | 사용 불가 장비 요구 | `EQUIPMENT_NOT_AVAILABLE` | 위반 0 |
| 4 | 제한/금기 운동 포함 | `SAFETY_EXCLUDED_EXERCISE_INCLUDED` | **위반 0 (무관용)** |
| 5 | 통증 부위 충돌 | envelope `excluded_exercise_ids` 대조 | **위반 0 (무관용)** |
| 6 | Safety BLOCKED 무시 | `PLAN_GENERATION_FORBIDDEN`, `STOP_AND_SEEK_HELP` | **위반 0 (무관용)** |
| 7 | 필수 입력 누락 처리 | `REQUIRED_INPUT_MISSING` → 계획 없음 | 100% |
| 8 | 비정상 입력 처리 | 계약 거부 또는 `validate_entry` 실패 | 100% |
| 9 | Agent 간 State 유실 | `collect_proposals` 역할 순서 재조립 | 100% |
| 10 | LangGraph 정상 종료 | 모든 실행이 `finalize`/`terminal` 도달 | 100% |
| 11 | 무한 반복 방지 | 그래프 DAG 토폴로지 + `repair_attempts<=1` | 구조적 증명 |
| 12 | Agent Exception 처리 | `V3_<ROLE>_FAILED` → fallback/terminal | 100% |

### 목표치 고정 (착수 전 확정, 사후 변경 금지)

- 안전 관련(4, 5, 6): **위반 0건**. 1건이라도 나오면 Phase 2 FAIL.
- 구조 관련(1, 9, 10, 11): **100%**.
- 실패 처리(7, 8, 12): **100% fail-closed**. 실패 시 성공 계획을 반환하면 FAIL.
- 제약 관련(2, 3): 위반 0건. 단 위반 시 서비스 결함/테스트 결함을 구분해 기록.

### Runner 설계 (핵심)

`build_v3_demo_runtime(..., chat_model=<주입>)`에 **결정적 scripted fake
BaseChatModel**을 주입한다. 이유:

- 실제 `compile_plan()`, `validate_plan_integrity()`, fallback provider,
  LangGraph 라우팅을 **전부 진짜로** 통과시킨다.
- LLM만 대체하므로 "LLM이 무엇을 내놓든 시스템이 안전한가"를 직접 시험할 수 있다.
- 비용 0, 완전 재현.

fake chat model은 case별로 다음 시나리오를 스크립트한다:

| 스크립트 | 목적 |
|---|---|
| `COMPLIANT` | 정상 제안 |
| `SAFETY_VIOLATING` | 제외된 운동을 굳이 포함 → validator가 막는지 |
| `DURATION_VIOLATING` | 요청 시간 초과 → validator가 막는지 |
| `PHASE_MISSING` | WARMUP/COOLDOWN 누락 → validator가 막는지 |
| `SCHEMA_INVALID` | 스키마 위반 출력 → `LLM_AGENT_SCHEMA_INVALID` |
| `TIMEOUT` | 응답 없음 → `V3_<ROLE>_TIMEOUT` |
| `EXCEPTION` | 예외 발생 → `V3_<ROLE>_FAILED` |
| `ROLE_VIOLATING` | Recovery가 prescriptions 제출 → 계약이 거부하는지 |

**이것이 이번 평가의 가장 중요한 설계 판단이다.** "LLM이 잘 하는가"가 아니라
"LLM이 잘못해도 시스템이 안전한가"를 재는 것이 배포 전 품질 평가의 본질이다.

### 결과 구조화

단순 PASS/FAIL이 아니라 실패 이유를 구조화한다:

```json
{
  "case_id": "SQ-SAFETY-001",
  "category": "safety_critical",
  "script": "SAFETY_VIOLATING",
  "passed": false,
  "failures": [
    {
      "check_code": "SAFETY_EXCLUDED_EXERCISE_INCLUDED",
      "severity": "CRITICAL",
      "expected": "excluded exercise never reaches final plan",
      "observed": "<위반 내용>",
      "defect_class": "SERVICE | TEST"
    }
  ]
}
```

`defect_class`를 반드시 채운다. 마스터 명세의 "서비스 결함과 테스트 결함 구분"
요구를 결과 파일 수준에서 강제하기 위함이다.

### 완료 기준

- [ ] 12개 항목 전부 테스트 존재
- [ ] `uv run pytest backend/tests/evaluation` 통과
- [ ] ruff / mypy 통과
- [ ] 기존 174개 테스트 회귀 없음
- [ ] 결과 JSON이 `results/`에 재현 가능하게 생성됨
- [ ] 서비스 코드 변경 0줄

---

## PHASE 3. Vector Search / RAG Evaluation (계획)

- Retriever와 Generation을 분리 평가한다.
- 지표: Recall@1/@3/@5, MRR, Metadata Filter Accuracy
- **해석 규칙(필수)**: Qdrant는 자격이 아니라 순위를 담당하므로 Recall 저하가 곧
  안전/자격 실패가 아니다. 보고서에 이 문장을 명시한다.
- 실행 방식: `qdrant-client` local 모드 + `DeterministicFakeEmbeddingAdapter`로
  배선 검증 → 실 임베딩 승인 후 수치 산출
- 산출물: `results/retrieval_metrics.json`, `results/retrieval_cases.csv`
- **fake 임베딩 수치를 검색 성능으로 보고하지 않는다.**

## PHASE 4. Multi-Agent Evaluation (계획)

- 지표: Agent Invocation Accuracy, Agent Role Consistency, State Consistency,
  Workflow Completion Rate, Coordinator Conflict Resolution Accuracy,
  Safety Compliance Rate, Structured Output Success Rate
- 근거 데이터: `InvocationAudit` + `V3GraphResult` (LangSmith 불필요)
- Conflict A~D 중 **A/D는 관측 지표**로만 집계한다. Recovery/Feasibility는
  advisory이므로 "따랐는가"를 PASS/FAIL로 판정하면 설계에 없는 요구가 된다.
  B(Safety BLOCKED)와 C(시간 초과)는 결정적 PASS/FAIL이다.
- Safety는 Judge가 아니라 deterministic evaluation으로 판정한다.

## PHASE 5. LLM-as-a-Judge (계획, 유료)

- 대상: Rule로 판정 불가한 최종 추천 품질만
- 항목 6종 1~5점 + Rubric 제공
- **Safety violation은 Judge 점수와 무관하게 FAIL**
- Judge Prompt/Model/버전을 결과에 저장
- 선행 조건: `OPENAI_API_KEY`, 예산 승인

## PHASE 6. Single vs Multi 비교 — 완료

결과: `docs/test/PHASE6_COMPARISON.md` (203 호출, 아키텍처당 28 run)
구현: `backend/tests/evaluation/runners/single_agent.py`,
`backend/tests/evaluation/comparison.py`, `comparison_cli.py`
공정성 테스트: `backend/tests/evaluation/test_comparison.py`

비교 대상:

| | 아키텍처 | LLM 호출 | pool 정보 |
|---|---|---|---|
| A | Single LLM | 1 | 출력 스키마를 채우는 데 필요한 4개 필드만 |
| B | Single Agent + RAG | 1 | production pool projection 전체 |
| C | Multi-Agent + RAG | 4 | production pool projection 전체 |

Baseline 공정성 조건 — 이것을 어기면 실험이 무의미해진다:

- Single Agent baseline을 **일부러 약하게 만들지 않는다.** baseline 지시문은
  새로 쓰지 않고 배포 중인 `ROLE_PROMPTS` 4개에서 조립한다. 제거한 문장은
  `_DROPPED_CLAUSES`에 사유와 함께 기록하고, 테스트가 "제거된 문장이 실제 배포
  프롬프트에 존재하는 문장인지"와 "계획 규칙이 함께 사라지지 않았는지"를 검증한다.
- 동일: LLM 모델, temperature, timeout, 토큰 상한, 사용자 입력, dataset,
  운동 데이터, pool, Output Schema
- 하나의 Agent가 Training/Recovery/Feasibility/Coordination 판단을 **하나의
  Context 안에서** 수행한다
- **동일한 compiler / integrity validator / evaluator / fallback을 통과**시킨다
- 기존 멀티에이전트 서비스를 Single Agent로 영구 수정하지 않는다.
  `runners/single_agent.py`를 별도로 둔다. **서비스 코드 변경 0줄.**

공정성을 완전히 만족시키지 못한 지점 2개 — 둘 다 C에 유리하며 보고서에 명시한다:

1. **Output Schema가 완전히 동일하지 않다.** `PlanSpec`은 canonical 순서의
   proposal_reference 3개를 구조적으로 요구한다. baseline은 자기 출력을
   TRAINING proposal로 감싸는 contract adapter를 거쳐야 배포 compiler에 들어간다.
   adapter는 advice를 만들어내지 않는다(advisory 2개는 "특화 에이전트 조언 없음"
   코드 하나만 싣는다). **이 제약 자체가 PHASE 6의 발견이다.**
2. **baseline에는 repair 라운드가 없다.** C는 1회 있다. PHASE 4 유료 실행
   14건 전부 `repair_attempts == 0`이었으므로 실측상 영향은 없었다.

측정 지표는 두 갈래로 분리해 보고한다. 합치면 PHASE 6의 질문이 사라진다:

- `llm_plan_rate` — 모델이 만든 계획이 integrity gate를 통과한 비율. **아키텍처의 성적**
- `plan_delivery_rate` — 사용자가 계획을 받은 비율(결정적 fallback 포함). **서비스의 성적**

Judge는 **blind**로 실행한다. 아키텍처를 식별시키는 유일한 payload 필드
(`advisory_codes`)를 양쪽 모두에서 제거한다. 그 대가로 PHASE 6의 judge 점수는
PHASE 5 수치와 직접 비교할 수 없다.

검증 가설(착수 전 고정): 단순 케이스에서는 차이가 작고, 복수·상충 조건에서는
Multi-Agent가 조건 충족률·안전성·일관성에서 우수하다.

**실측 결과: 확인되지 않았다.** conflict에서 B와 C 동률(1.00), complex에서는
B(1.00) > C(0.75), 안전성은 셋 다 1.00, structured output은 B(1.00) > C(0.893).
멀티에이전트가 우월한 축은 조건 충족률이 아니라 **품질**(judge 4.40 vs 4.08)이었다.

**가설에 맞지 않는 결과가 나와도 수정하거나 제외하지 않는다.** 수정하지 않았다.

## PHASE 7. Pairwise Judge — 완료

결과: `docs/test/PHASE7_PAIRWISE.md` / 산출물: `results/pairwise/`
구현: `backend/tests/evaluation/judge/pairwise.py`, `pairwise_cli.py`
테스트: `backend/tests/evaluation/test_pairwise.py`

PHASE 6의 pointwise 점수 차(C 4.40 vs B 4.08)는 5점 척도에서 작아, rubric에
어떻게 맞아떨어졌는지의 artifact일 수 있다. 두 계획을 나란히 놓고 고르게 하면
그 캘리브레이션 문제가 사라진다. 대신 **position bias**가 생긴다.

설계:

- Judge에게 Single/Multi를 알리지 않는다. payload에서 아키텍처를 구조적으로
  식별시키는 `advisory_codes`를 제거하고, 모델이 직접 쓴 `decision_codes` 중
  파이프라인 이름이 들어간 것은 **redact하고 그 건수를 보고**한다. 블라인딩을
  가정하지 않고 측정한다.
- 제시 위치는 case별로 **재현 가능하게 randomize**한다(case_id 해시).
- **모든 pair를 순서를 바꿔 두 번 평가**한다. 두 판정이
  - 같은 *계획*을 지목 → 실제 선호
  - 같은 *슬롯*을 지목 → 내용이 아니라 위치를 따라간 것 = position bias
  - 한쪽이 TIE → 무승부로 그대로 기록하며 승자 쪽으로 반올림하지 않는다
- **승리로 집계하는 것은 첫 번째 경우뿐이다.** 두 번째는 bias rate로 보고하며,
  이 수치가 첫 번째를 얼마나 믿을 수 있는지를 말해준다.
- 계획이 없는 아키텍처가 낀 pair는 **판정 제외**이며 무승부가 아니다.

집계: Single Win / Tie / Multi Win + DISAGREED(두 순서 불일치) + position bias rate,
category별·rubric 항목별 분리.

비용 구조: collect(그래프 실행 → blind payload 저장)와 judge를 분리했다.
`--judge-only`로 재채점하면 judge 호출만 든다. PHASE 6 실행도
`pairwise_payloads.json`을 남기므로 다시 그래프를 돌릴 필요가 없다.

**bias 탐지기가 실제로 작동하는지 먼저 증명한다.** `AlwaysFirstPairwiseJudge`는
항상 첫 번째를 고르는 모의 심사자이며, 테스트가 이것을 bias rate 1.0 /
agreement 0.0으로 잡아내는지 검증한다. 이 테스트가 없으면 bias rate 0.0이
"편향 없음"인지 "탐지기가 안 켜짐"인지 구분할 수 없다.

## PHASE 8. LangSmith — 완료

**결론: 워크플로 trace는 계속 사용하고, LLM span은 기본 OFF인 명시적 옵트인으로만 연다.**
결정 기록은 `docs/adr/0020-opt-in-langsmith-provider-tracing.md`다.

실측 결과 (`docs/test/LANGSMITH_TRACING.md`, `test_tracing.py`):

- **추적됨**: 노드 15개 전체. 세 specialist 각각 독립 span, coordinator,
  compile/validate, 라우팅 결정, 실패·fallback·repair 경로, 노드별 latency,
  state(envelope·pool·proposal·PlanSpec)
- **기본값에서 추적 안 됨**: prompt, 모델 원문 응답, provider 토큰.
- **옵트인에서 추가됨**: provider prompt·모델 응답 span. 로컬 tracer probe로 연결을 검증

Token Usage는 trace가 아니라 `InvocationAudit`에서 이미 얻고 있으므로
마스터 명세 PHASE 8 요구 항목 중 실질적으로 빠지는 것은 prompt 원문뿐이다.

`LLM_AGENTS_TRACING_ENABLED=false`가 기본값이며 production compose에는 ON 값을 넣지 않는다.
개발팀장·PM 승인은 2026-09-11 확보했다. LangSmith project의 보존·접근 정책을 확인하고
평가·staging에서만 켠다.

최소 실측은 `SQ-SIMPLE-001` 한 건을 Judge 없이 4회 호출 상한으로 수행했다. 실행은
`SUCCEEDED`, 27,472 tokens, 27.328초, repair 0, fallback 없음이었고 LangSmith에서 세 specialist와
coordinator의 `ChatOpenAI` span 4개를 확인했다. 상세는
`docs/test/PHASE8_LANGSMITH_LLM_SPAN.md`에 기록했다.

워크플로 trace 실행은 `LANGSMITH_API_KEY`로 가능하다. LLM span에는 추가로
`LLM_AGENTS_TRACING_ENABLED=true`가 필요하다.

## PHASE 9. Performance / Failure (계획)

- 지표: P50/P95 Latency, 평균 Token Usage, LLM Call Count,
  Workflow Completion Rate, Parsing Error Rate, Node Error Rate
- percentile은 **기존 `v3_evaluation.py`의 nearest-rank 구현을 재사용**한다.
  다시 구현하면 기존 golden test와 수치가 갈라진다.
- Failure case: Retriever 결과 없음, LLM Timeout, Parsing Error,
  Agent Exception, Empty/Invalid Input, Graph Loop, 외부 API 실패
- **평가 기준은 "좋은 답변을 내는가"가 아니라 "안전하게 종료/fallback 하는가"**
- 일부는 PHASE 2 fake chat model 스크립트로 지금 측정 가능

## PHASE 10. Human Calibration (계획)

- 대표 case 20~30건 추출 양식
- `case_id`, `human_score`, `judge_score`, `score_difference` 비교 구조
- **Human Label이 없으면 임의로 생성하지 않는다.** 빈 양식만 만든다.

## PHASE 11. 결과 산출 (계획)

```
results/
    evaluation_summary.json
    evaluation_cases.csv
    retrieval_metrics.json
    agent_metrics.json
    architecture_comparison.csv
    latency_metrics.json
    failed_cases.json
docs/test/
    TEST_SYSTEM_ANALYSIS.md   [완료]
    TEST_PLAN.md              [이 문서]
    TEST_RESULTS.md
```

`TEST_RESULTS.md` 필수 14개 절 + Single vs Multi 비교표 + Category별 결과.

미실행 Phase는 "미실행"으로 명시하고 추정치로 채우지 않는다.

---

## 리스크

| 리스크 | 영향 | 대응 |
|---|---|---|
| API Key·예산 미승인 | Phase 5~7 불가 | 0~4, 9를 무비용으로 완결, 나머지는 미실행 명시 |
| fake 임베딩 수치 오해 | 잘못된 성능 주장 | 보고서에 해석 제약 명시, 성능 수치로 보고 금지 |
| Single baseline 약화 | 실험 무의미 | 공정성 조건을 Phase 6 착수 전 체크리스트로 강제 |
| temperature=0 결정론 가정 | 재현성 과신 | 반복 실행 편차 측정 |
| 평가 로직 중복 구현 | 기존 golden과 수치 불일치 | 기존 `v3_evaluation.py` 재사용 |
| 테스트가 서비스 코드 수정 유발 | 평가 오염 | 결함은 기록만, 수정은 별도 이슈·PR |

---

## 소유권

`backend/app/domain/agents/**`, `backend/app/domain/rules/**`는 AI/데이터 리드
소유 영역이다. 이번 작업은 **해당 영역을 읽기만 하고 수정하지 않는다.**
신규 파일은 `backend/tests/evaluation/**`와 `docs/test/**`에만 생성한다.
