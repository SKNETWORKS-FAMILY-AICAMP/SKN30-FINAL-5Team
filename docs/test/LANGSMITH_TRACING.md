# LANGSMITH_TRACING.md

멀티에이전트 루틴 생성 실행을 LangSmith에서 확인하기 위한 조사 결과와 한계.
측정 기준 커밋: `chore/service-quality-evaluation-harness`.

**요약**: 워크플로 전체(노드 15개)는 추적된다. **LLM 호출 자체는 추적되지 않으며,
이는 버그가 아니라 의도적으로 차단된 것이다.**

---

## 1. 실측 결과

`backend/tests/evaluation/test_tracing.py`가 실제 그래프를 tracer와 함께 실행해
확인한 내용이다. 추정이 아니라 측정값이다.

### 1.1 추적되는 것 (span 15개)

```
LangGraph
├─ validate_entry          → after_entry
├─ parallel_agents
│   ├─ agent_training      ← 역할별 독립 span
│   ├─ agent_recovery
│   └─ agent_feasibility
├─ collect_proposals       → after_agents
├─ coordinator_agent
├─ compile                 → after_compile
├─ validate                → after_validation
└─ finalize
```

각 노드의 input/output에 `ConstraintEnvelope`, `ExercisePoolSnapshot`,
세 proposal, Coordinator `PlanSpec`, integrity 판정 결과가 담긴다.
실패 경로(`fallback`, `terminal`)와 repair 경로도 동일하게 나타난다.

마스터 명세 PHASE 8이 요구한 항목 대비:

| 요구 항목 | LangSmith trace | 대체 경로 |
|---|---|---|
| Agent Input / Output | **가능** (노드 단위) | — |
| State | **가능** | — |
| Coordinator 결과 | **가능** | — |
| Retriever 결과 | 부분 (pool의 `RetrievalMetadata`) | `retrieval_metrics.json` |
| Error | **가능** (failure_codes) | — |
| Retry | **가능** (repair 노드 진입 여부) | `InvocationAudit.attempt_count` |
| Latency | 노드 단위 **가능** | `InvocationAudit.latency_ms` |
| **Token Usage** | **불가** | `InvocationAudit.input/output_token_count` |
| **Prompt / 모델 원문 응답** | **불가** | 없음 (의도적) |

### 1.2 추적되지 않는 것과 그 이유

`backend/app/integrations/llm_agents/provider.py:188`

```python
# LangSmith is a transitive dependency of langchain-core. Disable it
# explicitly so ambient tracing settings cannot export prompt content.
with tracing_context(enabled=False):
    raw_output = await structured_model.ainvoke(...)
```

즉 **provider 호출은 명시적으로 tracing에서 제외된다.** 4회 LLM 호출이 발생한
실행에서 LLM span은 0개임을 테스트로 고정했다
(`test_the_provider_calls_are_not_traced`).

근거 문서:

- `docs/TECHNICAL_PLAN.md:65` — "checkpointer, 장기 memory, LangSmith SaaS 전송은
  별도 승인 없이는 포함하지 않는다."
- `docs/TECHNICAL_PLAN.md:346` — LangSmith tracing과 callbacks 명시적 비활성화
- `backend/app/integrations/README.md:21` — 동일 취지

## 2. 지금 할 수 있는 것

`LANGSMITH_API_KEY`만 설정하면 **서비스 코드 변경 없이** 1.1의 워크플로 trace를
얻을 수 있다.

```bash
export LANGSMITH_API_KEY=...          # 별도 발급 필요 (Secrets Manager에 없음)
export LANGSMITH_PROJECT=helkki-service-quality
export OPENAI_API_KEY=...             # docs/test/PAID_EVALUATION.md 참고
uv run python -m backend.tests.evaluation.paid_run_cli --confirm-spend
```

Experiment 이름은 `backend/tests/evaluation/tracing.py`에 고정되어 있다:
`multi-agent-v1`, `baseline-single-agent-v1`, `multi-agent-scripted-offline-v1`.

키가 없으면 tracing만 꺼진 채 평가는 그대로 수행된다. 마스터 명세의
"LangSmith 연결이 없어도 로컬 Evaluation은 수행 가능" 요구를 만족한다.

## 3. 결정이 필요한 사항

### 3.1 LLM span까지 보려면 서비스 코드 변경이 필요하다

`provider.py`의 `tracing_context(enabled=False)`를 설정값으로 게이트해야 한다.
이는 **두 가지 승인이 동시에 필요한 변경**이다.

1. **소유권**: `backend/app/integrations/**`는 개발팀장 승인 영역이며
   공유 계약에 해당한다 (`AGENTS.md` 3절).
2. **개인정보 정책**: `docs/TECHNICAL_PLAN.md`가 명시적으로 금지한 SaaS 전송을
   여는 변경이므로 PM 검토가 필요하다 (`AGENTS.md` 3절, 8절).

제안 형태(적용하지 않음, 검토용):

```python
# provider.py
with tracing_context(enabled=settings.llm_agents_tracing_enabled):
    ...
```

기본값 `False`를 유지하고 staging에서만 켜는 방식이면 production 동작은
바뀌지 않는다. **이 변경은 이번 작업에서 수행하지 않았다.**

### 3.2 전송되는 데이터의 성격

워크플로 trace만 켜도 다음이 LangSmith(외부 SaaS)로 나간다.

포함되지 않는 것 (설계상 보장):

- 생년월일, 만 나이, 이름, 이메일, 사용자 ID, 기기 ID
- 원시 웨어러블 샘플, GPS, 캘린더 텍스트
- prompt 원문, 모델 원문 응답

포함되는 것:

- `excluded_exercise_ids` — **불편 부위를 간접적으로 드러낸다**
- `recovery_ceiling` — **피로/컨디션 수준을 간접적으로 드러낸다**
- `safety_required_action_code` — REST/STOP 여부
- 요청 시간, 목표, 장소, 승인된 운동 후보 목록

직접 식별자는 없으나 **건강 관련 추론이 가능한 값이 포함된다.** 단독으로
개인을 특정할 수는 없지만, `AGENTS.md` 8절이 다루는 범주에 인접한다.
켜기 전 PM 확인을 권한다.

## 4. 권고

| 목적 | 권고 |
|---|---|
| 멀티에이전트 실행 흐름 확인 | **지금 가능.** LangSmith 키만 설정 |
| 노드별 latency·경로·실패 원인 | **지금 가능** |
| Token / Cost 집계 | LangSmith 불필요. `InvocationAudit` 사용 |
| prompt·모델 응답 확인 | 서비스 코드 변경 + 2건 승인 필요 |

3.1을 진행하지 않아도 마스터 명세 PHASE 8의 요구 항목 대부분이 충족된다.
Token Usage는 trace가 아니라 `InvocationAudit`에서 이미 얻고 있다.
