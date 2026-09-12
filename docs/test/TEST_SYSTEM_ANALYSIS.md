# TEST_SYSTEM_ANALYSIS.md

서비스 품질 평가(`docs/test/service_test_master_prompt.md`) PHASE 0 산출물이다.
**실제 구현을 읽고 확인한 사실만 기록한다.** 기획서에 있으나 코드에 없는 요소는
"미구현"으로 명시한다.

- 분석 기준 커밋: `6deb151` (develop)
- 분석 일자: 2026-09-10
- 분석 범위: `backend/app/domain/agents/**`, `backend/app/integrations/langgraph/**`,
  `backend/app/integrations/llm_agents/**`, `backend/app/integrations/qdrant/**`,
  `backend/app/domain/rules/**`, `backend/app/api/v1/**`, `backend/tests/**`

---

## 1. LangGraph Workflow

구현 위치: `backend/app/integrations/langgraph/graph.py`

`create_v3_graph()`가 `StateGraph(V3GraphState)`를 조립한다. **checkpointer=False**로
컴파일되어 상태 영속화와 부모 checkpoint 상속이 모두 꺼져 있다(stateless).

노드 목록(17개):

| 노드 | 함수 | 성격 |
|---|---|---|
| `validate_entry` | `nodes.validate_entry` | 결정적 |
| `parallel_agents` | `nodes.parallel_agents` | fan-out 더미 |
| `agent_training` / `agent_recovery` / `agent_feasibility` | `nodes.*_agent` | LLM |
| `collect_proposals` | `nodes.collect_proposals` | 결정적 fan-in |
| `coordinator_agent` | `nodes.coordinator_agent` | LLM |
| `compile` / `compile_repair` / `compile_fallback` | `nodes.compile_plan` | 결정적 |
| `validate` / `validate_repair` / `validate_fallback` | `nodes.validate_plan` | 결정적 |
| `coordinator_repair` | `nodes.coordinator_repair` | LLM (최대 1회) |
| `fallback` | `nodes.fallback` | 결정적 |
| `finalize` / `terminal` | `nodes.finalize` / `nodes.terminal` | 결정적 |

라우팅은 `routing.py`의 순수 함수 7개(`after_entry`, `after_agents`, `after_compile`,
`after_validation`, `after_fallback`, `after_fallback_compile`,
`after_fallback_validation`)로만 결정된다.

**무한 루프 방지 — 구조가 아니라 상태로 보장된다** (PHASE 2에서 실측 후 정정):

컴파일된 그래프는 **DAG가 아니다.** `validate_repair`가 `validate`와 같은
`after_validation` 라우터를 재사용하고 이 라우터의 선언된 반환 타입에
`coordinator_repair`가 포함되므로, 토폴로지에는 정확히 하나의 순환이 존재한다.

```
coordinator_repair -> compile_repair -> validate_repair -> coordinator_repair
```

실측으로 확인한 순환은 이 하나뿐이다(`test_the_repair_cycle_is_the_only_cycle`).

런타임에서 두 번째 repair가 불가능한 이유는 간선이 없어서가 아니라 **상태 조건**
때문이다.

- `after_validation`은 `state.get("repair_attempts", 0) == 0`일 때만
  `coordinator_repair`로 보낸다.
- `nodes.coordinator_repair`는 성공·타임아웃·예외·provider 실패 **모든 반환 경로**에서
  `repair_attempts: 1`을 설정한다.

따라서 `validate_repair`에서 `coordinator_repair`로 가는 간선은 존재하지만 도달
불가능하다. repair 이후 실패는 `fallback`으로만 가고 fallback 경로는 `finalize`
또는 `terminal`로만 나간다.

**이것이 중요한 이유**: 루프 한계가 단 하나의 상태 술어에 의존한다.
`repair_attempts` 증가가 어느 한 반환 경로에서라도 누락되면 순환이 열린다. 그래서
PHASE 2는 (1) 순환이 이것 하나뿐인지, (2) 라우터 가드가 유지되는지,
(3) `coordinator_repair`의 모든 `return`이 `repair_attempts`를 담는지를 각각
별도로 고정한다.

## 2. Agent 종류와 역할

실제 존재(코드 확인):

| 기획 명칭 | 실제 구현 | 위치 |
|---|---|---|
| Training Agent | **존재** `TrainingAgentAdapter` | `llm_agents/specialists.py` |
| Recovery Agent | **존재** `RecoveryAgentAdapter` | `llm_agents/specialists.py` |
| Feasibility Agent | **존재** `FeasibilityAgentAdapter` | `llm_agents/specialists.py` |
| Coordinator | **존재** `LangChainCoordinatorAdapter` | `llm_agents/coordinator.py` |
| **Safety Agent** | **미구현(의도적)** | 아래 참조 |

**Safety는 Agent가 아니다.** `SpecialistAgentTypeCode`는 `TRAINING`, `RECOVERY`,
`FEASIBILITY` 3개뿐이며, `tests/unit/test_v3_agent_contracts.py`의
`test_safety_agent_type_is_rejected`가 SAFETY 역할 자체를 거부한다. Safety는
`app/domain/rules/safety.py`의 결정적 `evaluate_safety()`가 그래프 **진입 전에**
`ConstraintEnvelope`로 고정하고, 그래프 **하류의** `validate_plan_integrity()`가
재확인한다. 이는 ADR-0015 및 `AGENTS.md` 11절 golden scenario 6과 일치한다.

ADR-0015 역할 분리(코드로 강제됨):

- Training만 `exercise_prescriptions`를 낸다.
- Recovery/Feasibility가 prescriptions를 담으면
  `SpecialistAgentProposal`의 model validator가 `ValueError`를 던진다.
- Recovery/Feasibility는 `adjustment_codes`(advisory)만 낸다. 결정적 강제 없음.

## 3. Agent Input / Output Schema

- Input: `SpecialistAgentInput` (`v3_contracts.py:493`)
  — `agent_type_code`, `constraint_envelope`, `envelope_hash`, `exercise_pool`,
  `pool_hash`, `regeneration_context`
- Output: `SpecialistAgentProposal` (`v3_contracts.py:546`)
  — `proposal_status_code`, `exercise_prescriptions`, `adjustment_codes`,
  `hard_constraint_codes`, `reason_codes`, `evidence_reference_codes`,
  `public_summary_code`, `proposal_hash`
- Coordinator Input: `CoordinatorInput` (`v3_contracts.py:687`)
- Coordinator Output: `PlanSpec` (`v3_contracts.py:747`)

모든 계약이 `ConfigDict(extra="forbid", frozen=True, strict=True)`이다.
자유 텍스트 필드가 없고, 모든 근거는 machine code다. `*_hash` 필드는 canonical JSON
SHA-256으로 자기 검증한다 → **구조화 출력 검증이 스키마 수준에서 이미 강제된다.**

`estimated_duration_seconds`는 서버가 파생한다(`derive_estimated_duration_seconds`).
LLM이 이 값을 고르지 못한다.

## 4. Graph State Schema

`V3GraphState` (`langgraph/state.py`, `TypedDict, total=False`).
`agent_outcomes`, `invocation_audits`, `integrity_validations`, `compiled_plans`는
`Annotated[..., operator.add]` reducer로 병렬 분기를 합친다.

**State 무결성의 핵심**: `collect_proposals`가 도착 순서가 아니라
`SPECIALIST_AGENT_ORDER`로 역할별 재조회를 하여 병렬 superstep interleaving과 무관하게
같은 결과를 만든다(코드 주석에 재현성 근거 명시). 이는 PHASE 2 "Agent 간 State 정보
유실" 테스트의 직접 대상이다.

`V3GraphInput`은 **DB 핸들과 PII를 담지 않는다**(dataclass docstring 명시). 따라서
평가 harness가 DB 없이 그래프를 구동할 수 있다 — 이번 평가 설계의 결정적 이점.

## 5. Coordinator / 최종 의사결정 Node

- LLM Coordinator: `LangChainCoordinatorAdapter.acoordinate()` / `.arepair()`
- **최종 결정권은 Coordinator에 없다.** `compile` → `validate` 순서로
  `compile_plan()`(`v3_compiler.py:174`)이 카탈로그 타이밍 기준으로 실제 소요시간을
  재계산하고, `validate_plan_integrity()`(`v3_validation.py:260`)가 27개
  `IntegrityViolationCode`로 판정한다. 통과해야만 `finalize`로 간다.
- Coordinator 출력에 대한 **유일한 결정적 게이트가 이 integrity validation**이며
  coordinator 상류에는 검증이 없다(ADR-0015, `domain/agents/AGENTS.md`).

## 6. Vector DB / Retriever

- Vector DB: **Qdrant** (`qdrant-client==1.18.0`), `app/integrations/qdrant/`
- Retriever: `ExerciseRetriever` Protocol (`domain/agents/retrieval.py:726`),
  구현 `QdrantExerciseRetriever` / `DatabaseBoundQdrantExerciseRetriever`
- Pool 조립: `QdrantExercisePoolSnapshotLoader` (`qdrant/snapshot_loader.py`)

**중요한 아키텍처 사실**: 모듈 docstring이 "PostgreSQL-authoritative
ExercisePoolSnapshot composition with Qdrant ranking"이다. **자격(eligibility)은
PostgreSQL이 정하고 Qdrant는 순위(ranking)만 매긴다.**
`PostgreSQLExercisePoolSourcePort.load_eligible()`이 후보 집합을 만들고, Qdrant
결과는 그 안에서 순서를 바꿀 뿐이다. `deterministic_retrieval_fallback`이 Qdrant
실패 시 결정적 순서로 대체한다.

→ 그러므로 PHASE 3의 Recall@k는 **"정답 운동을 검색이 놓쳤는가"가 아니라
"정답 운동을 상위에 올렸는가"** 를 재는 지표로 해석해야 한다. 검색 실패가 곧
안전/자격 실패가 아니다. 보고서에서 이 구분을 반드시 명시한다.

기본값은 비활성이다: `settings.qdrant_enabled = False`.

## 7. Embedding Model

- 계약: `EmbeddingContract` (`qdrant/embedding.py`) — provider, model_version,
  vector_dimension, distance_metric
- 운영 어댑터: `OpenAIEmbeddingAdapter` (`qdrant/openai_embedding.py`),
  모델은 `settings.embedding_model_version`로 주입되며 기본값은 `"unconfigured"`
- 테스트 어댑터: `DeterministicFakeEmbeddingAdapter` — SHA-256 기반 결정적 벡터,
  자격증명 불필요

**한계**: fake 임베딩으로 계산한 Recall/MRR은 검색 품질이 아니라 파이프라인 배선을
검증할 뿐이다. 실제 임베딩 없이 산출한 수치를 검색 성능으로 보고하면 안 된다.

## 8. RAG 사용 위치

RAG는 **답변 생성용 context 주입이 아니라 후보 pool 구성**에 쓰인다.

```
PostgreSQL 자격 후보 → Qdrant 벡터 순위 → ExercisePoolSnapshot(pool_hash)
    → 세 Agent의 입력 + Coordinator 입력 + integrity validator의 대조 기준
```

Agent는 pool 밖 운동을 만들 수 없고(`_validate_prescription_constraints`),
validator가 `EXERCISE_OUTSIDE_POOL`로 재확인한다. 즉 **groundedness가 스키마로
강제되는 구조**라 PHASE 5의 Groundedness 항목은 LLM Judge보다 결정적 검사가 우선한다.

## 9. 사용 LLM

- 어댑터: `langchain-openai==1.5.1`의 `ChatOpenAI` (`llm_agents/openai.py`)
- 모델: `settings.llm_agents_model_code` (기본 `"unconfigured"`),
  `settings.llm_agents_approved_model_codes` allowlist 안에 있어야만 생성됨
- 호출 파라미터(고정): `temperature=0`, `max_retries=0`(재시도는
  `StructuredChatInvoker`가 1회만 소유), `disable_streaming=True`,
  `max_completion_tokens=settings.llm_agents_max_output_tokens`(기본 1200),
  `timeout=settings.llm_agents_timeout_seconds`(기본 5.0)
- 별도 서술용 LLM: `settings.llm_model_code` (기본 `"gpt-5.6-terra"`), 기본 비활성

**게이트**: `openai_demo_gates_ready()` / `openai_shadow_gates_ready()`가 모두
만족되지 않으면 provider 객체 자체가 생성되지 않는다(`None` 반환). 즉 실수로
API 비용이 발생할 수 없는 구조다.

**재현성 관점**: `temperature=0` + 구조화 출력 + 서버 파생 필드 → LLM 응답 변동폭이
작다. 다만 0이 결정론을 보장하지는 않으므로 반복 실행 편차를 측정해야 한다.

## 10. Prompt

`llm_agents/prompts.py`의 `ROLE_PROMPTS` 4개, 각각 버전 태그 보유:

| 역할 | prompt_version |
|---|---|
| TRAINING | `v3-training-prompt-v9` |
| RECOVERY | `v3-recovery-prompt-v3` |
| FEASIBILITY | `v3-feasibility-prompt-v3` |
| COORDINATOR | `v3-coordinator-prompt-v5` |

`messages_for()`가 `prompt_version`, `output_schema_version`, `input`을 canonical JSON
(sort_keys, ensure_ascii)으로 직렬화한다 → 동일 입력이면 동일 프롬프트 바이트.

프롬프트는 절대 클라이언트로 반환되지 않는다(`AGENTS.md` 8절).

## 11. Safety 관련 Rule

`app/domain/rules/safety.py`, 결정적 순수 함수
`evaluate_safety(context, candidate, rule_set)`.

판정 순서(먼저 걸리면 즉시 종료):

1. `red_flag_present` → `STOP_AND_SEEK_HELP`
2. `EMERGENCY_REACTION_CODES` → `STOP_AND_SEEK_HELP`
3. `ACUTE_MUSCULOSKELETAL_REACTION_CODES` 또는 SEVERE 불편 → `REST`
4. 불편/주의부위 없음 → `PASS`
5. rule_set 없음/비가용 → `_rules_unavailable_evaluation` (fail-closed)
6. 승인된 rule 매칭 → EXCLUDE/CAUTION 집계
   - 전부 EXCLUDE → `BLOCKED` + `REST` + `veto=True`
   - 일부 → `REVISE`, `veto = bool(excluded)`

**LLM이 개입할 수 없다.** 결과는 `ConstraintEnvelope`로 굳어지고
(`plan_generation_allowed`, `excluded_exercise_ids`, `safety_required_action_code`),
`envelope_hash`가 canonical hash로 자기 검증하며, `ConstraintEnvelope`의
model validator가 `plan_generation_allowed and safety_required_action_code is not None`을
금지한다.

이중 방어:

- 상류: `validate_entry`가 `plan_generation_allowed=False` 또는 REST/STOP이면
  즉시 `terminal`
- 하류: `validate_plan_integrity`가 `SAFETY_EXCLUDED_EXERCISE_INCLUDED`,
  `STOP_AND_SEEK_HELP`, `PLAN_GENERATION_FORBIDDEN`으로 재판정

## 12. 운동 추천 생성 과정

```
DailyCheckin/Profile
  → evaluate_safety()                    [결정적]
  → ConstraintEnvelope.create()          [hash 고정]
  → PostgreSQL load_eligible()           [자격]
  → Qdrant 순위 → ExercisePoolSnapshot   [pool_hash 고정]
  → validate_entry                       [결정적 게이트]
  → Training | Recovery | Feasibility    [LLM 병렬, 각 node_timeout_seconds]
  → collect_proposals                    [역할 순서로 재조립]
  → coordinator_agent                    [LLM 1회]
  → compile_plan()                       [카탈로그 타이밍으로 소요시간 재계산]
  → validate_plan_integrity()            [27개 violation code]
      ├ passed        → finalize
      ├ repairable & repair_attempts==0 → coordinator_repair (1회)
      └ 그 외          → fallback [결정적] → compile → validate → finalize/terminal
```

시간 규칙: 요청 시간 ±`DURATION_TOLERANCE_SECONDS`(5분) 안이면 통과, 밖이면 실패.
`AGENTS.md` 7절 product invariant와 일치한다.

## 13. API Endpoint

`/api/v1` 하위. 결정 관련 주요 엔드포인트(`app/api/v1/decisions.py`):

| 메서드 | 경로 | 용도 |
|---|---|---|
| POST | `/api/v1/decisions` | 결정 생성 |
| GET | `/api/v1/decisions` | 당일 결정 조회 |
| POST | `/api/v1/decisions/...` | 재생성 |
| GET | `/api/v1/decisions/{decision_id}` | 단건 조회 |

그 외 `routines`, `workouts`, `weekly_plans`, `weekly_reports`, `daily_contexts`,
`profiles`, `exercises` 등 18개 라우터.

**이번 평가는 HTTP 계층이 아니라 그래프 경계에서 수행한다.** HTTP 경로는 인증·DB·
Qdrant·LLM을 모두 요구하지만, `V3GraphInput`은 순수 Pydantic 객체라 DB 없이 구동된다.
API 계약 회귀는 기존 `backend/tests/api/**`가 이미 담당한다.

## 14. 기존 테스트 코드

`backend/tests/` 아래 **174개 테스트 파일**. `unit/`, `api/`, `integration/`,
`scenarios/`. pytest marker: `integration`(PostgreSQL 필요),
`qdrant_integration`.

V3/agent 직접 관련 기존 테스트(주요):
`test_v3_langgraph_topology.py`, `test_v3_langgraph_parallel_agents.py`,
`test_v3_langgraph_repair.py`, `test_v3_langgraph_fallback.py`,
`test_v3_langgraph_privacy.py`, `test_v3_integrity_validator.py`,
`test_v3_agent_contracts.py`, `test_v3_coordinator_contracts.py`,
`test_v3_plan_compiler.py`, `test_v3_evaluation.py`, `test_safety.py`,
`scenarios/test_safety_golden.py`, `scenarios/test_v3_shadow_evaluation_golden.py`

**이미 존재하는 평가 인프라(재사용 대상, 신규 작성 금지)**:

- `app/modules/decisions/v3_shadow.py` — 실행 결과 투영(role별 invocation,
  usage, safety, latency)
- `app/modules/decisions/v3_evaluation.py` — p50/p95 nearest-rank percentile,
  cost 계산, privacy 검증, markdown 요약
- `app/modules/decisions/v3_evaluation_fixtures.py` — 18개 시나리오 synthetic
  fixture 번들, `FIXED_TIME = 2026-08-25T09:00Z`
- `scripts/run_v3_shadow_evaluation.py` — CLI, `--allow-provider-calls` 명시
  opt-in

기존 fixture 시나리오 코드에 이미 `HEALTHY_ORIGINAL`,
`LIMITED_TIME_DURATION_PRESERVED`, `KNEE_LOAD_EXCLUDED_GOAL_PRESERVED`,
`WEARABLE_MISSING_MANUAL_FALLBACK`, `REQUIRED_LLM_FAILURE_FALLBACK`,
`SAFETY_VETO_PRECEDENCE`, `QDRANT_TIMEOUT_POOL_FALLBACK` 등이 있다. 신규 dataset은
이 코드 체계를 이어받는다.

## 15. LangSmith 사용 여부

**사용하지 않는다. 그리고 이는 실수가 아니라 승인된 정책이다.**

- `llm_agents/provider.py:186`: `with tracing_context(enabled=False):`로 감싸
  ambient 환경변수가 프롬프트 내용을 유출하지 못하게 **명시적으로 차단**한다.
- `openai.py`: `callbacks=[]`
- `graph.py`: `config={"callbacks": []}`
- `docs/TECHNICAL_PLAN.md:65`: "checkpointer, 장기 memory, LangSmith SaaS 전송은
  별도 승인 없이는 포함하지 않는다."
- `docs/TECHNICAL_PLAN.md:346`: LangSmith tracing과 callbacks 명시적 비활성화

→ **PHASE 8은 "설정하기"가 아니라 "설정하지 않는 근거와 대체 수단을 문서화하기"로
수행한다.** LangSmith를 켜려면 PM·개발팀장 승인이 선행되어야 한다. 마스터 명세도
"LangSmith 연결이 없어도 로컬 Evaluation은 수행 가능하도록 만든다"고 요구한다.

**대체 내부 trace는 이미 있다**: `InvocationAudit`(role, phase, status, attempt,
latency_ms, input/output token, failure_code)이 그래프 상태에 누적되고
`V3GraphResult.invocation_audits`로 나온다. 마스터 명세 PHASE 8이 요구한 항목 중
Agent Input/Output, State, Coordinator 결과, Token Usage, Latency, Error, Retry가
모두 여기서 얻어진다. Retriever 결과는 `RetrievalMetadata`에 있다.

---

## 16. 테스트 대상 범위 결정

### 16.1 이번 평가가 다루는 것

| 범위 | 근거 |
|---|---|
| 그래프 경계(`V3GraphInput` → `V3GraphResult`) | DB·PII 비의존, 재현 가능 |
| 결정적 계약·검증(스키마, envelope, integrity) | 코드로 판정 가능 |
| Safety 불변식 | product invariant, LLM 개입 불가 |
| 실패·fallback 경로 | fail-closed 설계의 핵심 |
| Retriever 순위 품질 | Qdrant local 모드로 가능 |
| Multi-agent workflow 지표 | `InvocationAudit` 재사용 |
| Single vs Multi 비교 | 별도 runner, 동일 evaluator |

### 16.2 이번 평가가 다루지 않는 것(과 그 이유)

- **HTTP/인증/DB 통합 경로**: 기존 `tests/api/**`, `tests/integration/**`이 담당.
  로컬 PostgreSQL 미기동(확인함: `localhost:5432` 연결 실패).
- **프론트엔드**: 별도 소유자 영역(`AGENTS.md` 3절).
- **LangSmith 실제 연동**: 승인 필요(15절).
- **의학적 정확성 판정**: 제품이 진단·처방을 하지 않으므로 평가 항목이 아니다.

### 16.3 환경 제약(실측)

| 항목 | 상태 | 영향 |
|---|---|---|
| Python | 3.12.13 (uv) | 정상 |
| PostgreSQL `localhost:5432` | **연결 실패** | DB 의존 평가 불가 |
| `OPENAI_API_KEY` | `.env`에 **없음** | LLM 실호출 평가 불가 |
| `llm_agents_enabled` | 기본 `False` | provider 생성 차단 |
| `qdrant_enabled` | 기본 `False` | 벡터 검색 기본 비활성 |
| `embedding_model_version` | `"unconfigured"` | 실 임베딩 없음 |
| LangSmith | 정책상 비활성 | PHASE 8 문서화만 |

→ **PHASE 0~2, 9(실패 경로 일부)는 지금 바로 오프라인 실행 가능.**
→ PHASE 3은 Qdrant local + fake embedding으로 배선만 검증 가능(수치는 성능 아님).
→ PHASE 5~7은 API Key와 예산 승인이 선행되어야 한다.

### 16.4 평가 설계의 핵심 이점

`build_v3_demo_runtime(settings, execution_profile=..., chat_model=<주입>)`이
**chat_model을 주입받는다**(`demo_runtime.py:367`). 따라서:

- 오프라인: 결정적 scripted fake `BaseChatModel` 주입 → 전체 그래프를 실제
  compiler·validator·fallback과 함께 무비용 구동
- 유료: 실제 `ChatOpenAI` 주입 → 동일 코드 경로

**서비스 코드를 Single Agent로 영구 수정할 필요가 없다.** baseline runner는
동일한 `ConstraintEnvelope` + `ExercisePoolSnapshot` + 동일 모델·도구 접근으로
하나의 컨텍스트에서 Training/Recovery/Safety/Feasibility 판단을 수행하게 만들고,
출력은 동일한 `PlanSpec` 스키마로 받아 **동일한 compiler·validator·evaluator**를
통과시킨다. 차이는 오직 의사결정 architecture다.

---

## 17. 발견 사항 (서비스 결함 아님, 평가 설계상 유의점)

1. **Recall@k 해석 주의**: Qdrant는 자격이 아니라 순위만 담당(6절). 검색 지표를
   안전 지표처럼 읽으면 안 된다.
2. **Safety veto 검증 지점 고정**: golden scenario 6의 강제 지점은 coordinator
   **하류**의 integrity validation이다(ADR-0015). coordinator 상류에 검사를 두는
   테스트는 이 시나리오를 만족시키지 못한다.
3. **Recovery/Feasibility는 advisory**: adjustment_codes에 결정적 강제가 없다.
   "Coordinator가 Recovery 권고를 따랐는가"를 PASS/FAIL로 판정하면 설계에 없는
   요구를 테스트하는 것이 된다. 관측 지표로만 집계한다.
4. **temperature=0은 결정론이 아니다**: 반복 실행 편차를 별도로 측정해야 한다.
5. **기존 evaluation 모듈 재사용 필수**: percentile·cost·privacy 로직을 다시 짜면
   기존 golden test와 수치가 갈라진다.

---

## 18. 다음 단계

PHASE 1(Evaluation Dataset)로 진행한다. 상세 계획은 `docs/test/TEST_PLAN.md`.
이 단계에서 서비스 코드는 수정하지 않았다.
